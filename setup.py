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
                      'pyyaml'],
    package_data={'model': ['config/*']},
)