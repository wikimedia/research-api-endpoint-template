# Note: this can be ignored for now -- it is here to support future package management
# For now, requirements.txt handles the dependencies

from setuptools import setup

setup(
    name='model',
    version='0.0.1',
    url='https://github.com/geohci/research-api-endpoint-template',
    license='MIT License',
    maintainer='Isaac J.',
    maintainer_email='isaac@wikimedia.org',
    description='Generic API template for Wikimedia Research',
    long_description='',
    packages=['model'],
    install_requires=['fasttext',
                      'flask',
                      'flask_cors',
                      'mwapi',
                      'pyyaml',
                      'uwsgi'],
    package_data={'model': ['config/*']},
)