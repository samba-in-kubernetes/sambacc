from setuptools import setup, find_packages

setup(
    name="sambacc",
    version="0.1",
    author="John Mulligan <phlogistonjohn@asynchrono.us>",
    description="Samba Container Configurator",
    packages=find_packages(),
    entry_points={
        "console_scripts": ["samba-container-config=sambacc.main:main"],
    },
)
