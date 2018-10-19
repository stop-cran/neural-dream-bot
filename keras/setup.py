from setuptools import find_packages, setup

setup(
    name='neural_dream',
    version='1.0',
    install_requires=['Keras', 'argparse', 'scipy', 'tensorflow', 'google-cloud-storage', 'imageio', 'six'],
    packages=find_packages(),
    include_package_data=True,
    description='Neural style transfer'
)
