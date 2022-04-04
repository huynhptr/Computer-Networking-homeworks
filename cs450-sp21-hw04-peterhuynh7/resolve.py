"""
resolve.py: a recursive resolver built using dnspython
"""

import argparse

import dns.message
import dns.name
import dns.query
import dns.rdata
import dns.rdataclass
import dns.rdatatype

FORMATS = (("CNAME", "{alias} is an alias for {name}"),
           ("A", "{name} has address {address}"),
           ("AAAA", "{name} has IPv6 address {address}"),
           ("MX", "{name} mail is handled by {preference} {exchange}"))

# current as of 25 October 2018
ROOT_SERVERS = ("198.41.0.4",
                "199.9.14.201",
                "192.33.4.12",
                "199.7.91.13",
                "192.203.230.10",
                "192.5.5.241",
                "192.112.36.4",
                "198.97.190.53",
                "192.36.148.17",
                "192.58.128.30",
                "193.0.14.129",
                "199.7.83.42",
                "202.12.27.33")

MAX_TIMEOUT = 3  # maximum seconds to wait for a response

exact_match_cache = {}  # example: uic.edu uic.edu
tld_cache = {}  # example: uic.edu illinois.edu


def collect_results(name: str) -> dict:
    """
    This function parses final answers into the proper data structure that
    print_results requires. The main work is done within the `lookup` function.
    """
    full_response = {}
    target_name = dns.name.from_text(name)
    # lookup CNAME
    response = lookup(target_name, dns.rdatatype.CNAME)
    cnames = []
    for answers in response.answer:
        for answer in answers:
            cnames.append({"name": answer, "alias": name})
    # lookup A
    response = lookup(target_name, dns.rdatatype.A)
    arecords = []
    for answers in response.answer:
        a_name = answers.name
        for answer in answers:
            if answer.rdtype == 1:  # A record
                arecords.append({"name": a_name, "address": str(answer)})
    # lookup AAAA
    response = lookup(target_name, dns.rdatatype.AAAA)
    aaaarecords = []
    for answers in response.answer:
        aaaa_name = answers.name
        for answer in answers:
            if answer.rdtype == 28:  # AAAA record
                aaaarecords.append({"name": aaaa_name, "address": str(answer)})
    # lookup MX
    response = lookup(target_name, dns.rdatatype.MX)
    mxrecords = []
    for answers in response.answer:
        mx_name = answers.name
        for answer in answers:
            if answer.rdtype == 15:  # MX record
                mxrecords.append({"name": mx_name,
                                  "preference": answer.preference,
                                  "exchange": str(answer.exchange)})

    full_response["CNAME"] = cnames
    full_response["A"] = arecords
    full_response["AAAA"] = aaaarecords
    full_response["MX"] = mxrecords

    return full_response


def lookup(target_name: dns.name.Name,
           qtype: dns.rdatatype.RdataType) -> dns.message.Message:
    """
    Ask root servers and any subsequent name servers to find answers
    """
    response = ""
    for root in ROOT_SERVERS:
        try:
            found, response = ask(target_name, qtype, root)
        except dns.exception.Timeout as exception:
            raise exception
        if found:
            return response
    return response


def ask(target_name: dns.name.Name, qtype: dns.rdatatype, destination_ip: str):
    """
    The main worker of this program.
    A recursive function takes name and type of the request and send the
    request to the destination ip address.
    Return a tuple of query success/fail (true/false) status and the response.
    """
    response: dns.message.Message  # hold the answer

    tld = get_tld(target_name.to_text())
    if tld in tld_cache and destination_ip in ROOT_SERVERS:
        # check top level domain cache for answer
        response = tld_cache[tld]
    else:
        outbound_query = dns.message.make_query(target_name, qtype)

        key = str(outbound_query.question[0]) + destination_ip
        if key in exact_match_cache:
            # check cache for exact matched answers
            response = exact_match_cache[key]
        else:
            try:
                ask.count += 1  # update queries count
                response = dns.query.udp(outbound_query,
                                         destination_ip, MAX_TIMEOUT)
                exact_match_cache[key] = response  # update cache

                if destination_ip in ROOT_SERVERS:
                    # update tld_cache
                    tld_cache[get_tld(target_name.to_text())] = response

            except dns.exception.Timeout as exception:
                raise exception

    if response.rcode() != dns.rcode.NOERROR:
        # error response
        return False, response

    if dns.flags.AA in response.flags:
        cname_rr = get_cname(response)  # if get CNAME in ANSWER section

        if (not have_answer(response) or  # response has NXDOMAIN rcode
                type_matched(response, qtype) or  # answer found
                cname_rr is None):  # rarely get to this point
            return True, response

        # ask for something else(A, AAAA, MX) but get CNAME instead
        # return result of CNAME
        return True, lookup(
            dns.name.from_text(str(cname_rr)), qtype)

    # get NS records from AUTHORITY section
    authority_ns = get_ns_from_authority(response.authority)

    # to hold the name servers that don't have an ip address
    # in ADDITIONAL section
    authorities_without_ip = []

    # query name servers that have ip address in ADDITIONAL section
    for ns1 in authority_ns:
        a_rr = get_a_from_additional(response.additional, ns1)
        if a_rr is not None:
            found_a, a_res = ask(target_name, qtype, str(a_rr[0]))
            if found_a:
                return True, a_res
        else:
            # when ip address for this NS not found in ADDITIONAL
            authorities_without_ip.append(ns1)

    # find A records of remaining NSs
    for ns2 in authorities_without_ip:
        ns_ip = lookup(dns.name.from_text(str(ns2)),
                       dns.rdatatype.A).answer[0][0]  # won't be None
        found_ns, ns_res = ask(target_name, qtype, str(ns_ip))
        if found_ns:
            return True, ns_res

    return False, response


ask.count = 0  # hold queries count to test caches


def get_tld(link_name: str) -> str:
    """
    Get the top level domain string(ex. com, net, edu) from a link
    """
    return link_name.split('.')[-2]


def get_cname(res: dns.message.Message):
    """
    Get the CNAME record in ANSWER section
    """
    for answers in res.answer:
        for answer in answers:
            if answer.rdtype == dns.rdatatype.CNAME:
                return answer
    return None


def have_answer(res: dns.message.Message) -> bool:
    """
    Check if the ANSWER section is empty or not
    """
    return res.answer != []


def type_matched(res: dns.message.Message, ans_type: dns.rdatatype) -> bool:
    """
    Check if a message matches a type
    """
    for answers in res.answer:
        for answer in answers:
            if answer.rdtype == ans_type:
                return True
    return False


def get_ns_from_authority(authorities):
    """
    Get all the NS resource records in AUTHORITY section
    """
    result = []
    for authority in authorities:  # usually only have 1
        for record in authority:
            if record.rdtype == dns.rdatatype.NS:
                result.append(record)
    return result


def get_a_from_additional(additionals: list, name):
    """
    Get the first A resource record that matches the name
    """
    for record in additionals:
        if record.rdtype == dns.rdatatype.A and str(record.name) == str(name):
            return record
    return None


def get_result_strings(results: dict) -> list:
    """
    This function is similar to print_results(), but returns the string instead
    """
    results = []
    for rtype, fmt_str in FORMATS:
        for result in results.get(rtype, []):
            results.append(fmt_str.format(**result))
    return results


def print_results(results: dict) -> None:
    """
    take the results of a `lookup` and print them to the screen like the host
    program would.
    """
    for rtype, fmt_str in FORMATS:
        for result in results.get(rtype, []):
            print(fmt_str.format(**result))


def main():
    """
    if run from the command line, take args and call
    printresults(lookup(hostname))
    """
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("name", nargs="+",
                                 help="DNS name(s) to look up")
    argument_parser.add_argument("-v", "--verbose",
                                 help="increase output verbosity",
                                 action="store_true")
    program_args = argument_parser.parse_args()
    for a_domain_name in program_args.name:
        try:
            print_results(collect_results(a_domain_name))
        except (dns.exception.Timeout,
                dns.exception.FormError,
                dns.exception.DNSException,
                dns.exception.SyntaxError,
                dns.exception.TooBig,
                dns.exception.UnexpectedEnd):
            continue


if __name__ == "__main__":
    main()
