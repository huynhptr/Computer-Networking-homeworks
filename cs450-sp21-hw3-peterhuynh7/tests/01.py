test = {
  'name': 'Check if war.py exists',
  'points': 0,
  'suites': [
    {
      'cases': [
        {
          'code': r"""
          >>> assert "war.py" in os.listdir(".")
          """,
          'hidden': False,
          'locked': False
        }
      ],
      'scored': False,
      'setup': r"""
      >>> import os
      """,
      'teardown': '',
      'type': 'doctest'
    }
  ]
}
