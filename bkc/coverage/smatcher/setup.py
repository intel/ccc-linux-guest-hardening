from setuptools import setup
from smatcher import __version__, __license__, __author__, __email__

setup(name='smatcher',
      version=__version__,
      description='Smatcher - line coverage smatch analysis and aggregation tool',
      url='https://github.com/intel/ccc-linux-guest-hardening',
      author=__author__,
      author_email=__email__,
      license=__license__,
      packages=['smatcher'],
      entry_points = {
        'console_scripts': ['smatcher=smatcher.__init__:main'],
      },
      zip_safe=False)
