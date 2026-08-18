from setuptools import setup, find_packages
import os
import pathlib

CURRENT_DIR = pathlib.Path(__file__).parent
README = (CURRENT_DIR / "README.md").read_text()

env = os.environ.get('source')


def get_dependencies():
    dependency = [
        "python-barcode==0.15.1",
        "APScheduler==3.11.0",
        "redis==6.4.0",
        "aiohttp==3.13.2",
        "weasyprint==69.0",
        "qrcode[pil]==8.2"
    ]

    if env and env == "code":
        return dependency

    return dependency + []


setup(
    name='mweb-builtin',
    version='0.0.1',
    url='https://github.com/banglafighter/mweb-builtin',
    license='Apache 2.0',
    author='Bangla Fighter',
    author_email='banglafighter.com@gmail.com',
    description='Built-in helpers for email, task scheduling, and other useful features needed for development.',
    long_description=README,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=get_dependencies(),
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
    ]
)
