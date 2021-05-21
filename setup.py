from setuptools import setup, find_packages

setup(
    name="sambacc",
    version="0.1",
    author="John Mulligan",
    author_email="phlogistonjohn@asynchrono.us",
    description="Samba Container Configurator",
    # why does 'setup.py check' require this url field?
    url="mailto:phlogistonjohn@asynchrono.us",
    packages=find_packages(),
    entry_points={
        "console_scripts": ["samba-container=sambacc.commands.main:main"],
    },
    data_files=[
        (
            "share/sambacc/examples",
            ["examples/example1.json", "examples/minimal.json"],
        )
    ],
)
