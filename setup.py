from setuptools import setup

setup(
    name = 'gopro2gpx',
    author = 'David Johnson',
    url = 'https://github.com/znoop333/gopro2gpx',
    version = "0.1",
    packages = ['gopro2gpx'],
    entry_points = {
        'console_scripts': ['gopro2gpx = gopro2gpx.__main__:main']
    }
)
