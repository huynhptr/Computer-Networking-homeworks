test = {
  'name': 'Check if hw5.py exists',
  'points': 0,
  'suites': [
    {
      'cases': [
        {
          'code': r"""
          >>> assert "hw5.py" in os.listdir(".")
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
