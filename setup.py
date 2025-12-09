
from setuptools import setup, find_packages

setup(
    name="jira-analytics-tool",
    version="1.0.0",
    author="Stepan_S",
    # УБРАТЬ: packages=find_packages(),
    # ДОБАВИТЬ:
    py_modules=["jira_analyzer"],  # <-- Явно указываем имя файла (без .py)
    
    install_requires=[
        "requests>=2.25.0",
        "matplotlib>=3.5.0",
        "numpy>=1.21.0",
    ],
    entry_points={
        "console_scripts": [
            "jira-analyzer=jira_analyzer:main",
        ],
    },
)

