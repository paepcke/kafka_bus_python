import multiprocessing
from setuptools import setup, find_packages

test_requirements = ['sentinels>=0.0.6', 'nose>=1.0', 'python-dateutil>=2.2']

setup(
    name = "kafka_bus_python",
    version = "0.1.1",
    packages = find_packages(),

    # Dependencies on other packages:
    setup_requires   = ['nose>=1.1.2'],
    tests_require    = test_requirements,
    install_requires = ['kafka-python>=0.9.3', 
			'configparser>=3.3.0r2', 
			'argparse>=1.2.1', 
			'unidecode>=0.04.14', 
			] + test_requirements,

    # Unit tests; they are initiated via 'python setup.py test'
    test_suite       = 'nose.collector', 

    #data_files = [('pymysql_utils/data', datafiles)],

    package_data = {
        # If any package contains *.txt or *.rst files, include them:
     #   '': ['*.txt', '*.rst'],
        # And include any *.msg files found in the 'hello' package, too:
     #   'hello': ['*.msg'],
    },

    # metadata for upload to PyPI
    author = "Andreas Paepcke",
    author_email = "paepcke@cs.stanford.edu",
    description = "Provides a software bus type API over Kafka.",
    license = "BSD",
    keywords = "Kafka, OpenEdX",
    url = "https://github.com/paepcke/kafka_bus_python",   # project home page, if any
)
