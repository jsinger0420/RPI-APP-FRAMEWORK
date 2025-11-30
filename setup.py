from setuptools import setup, find_packages
import os

setup(
    name="rpi-app-framework",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Modular framework for all Raspberry Pi models with hardware managers (LED, WiFi, Motor, Web)",
    long_description=open("README.md").read() if os.path.exists("README.md") else "A cross-compatible framework for RPi Pico and full RPi apps.",
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/rpi-app-framework",
    packages=find_packages(),  # Auto-discovers rpi_app_framework/
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Development Status :: 4 - Beta",
        "Topic :: System :: Hardware",
    ],
    python_requires=">=3.6",
    install_requires=[
        "RPi.GPIO; sys_platform == 'linux'",  # For full RPi GPIO
        "gpiozero; sys_platform == 'linux'",  # For PWM/LED on full RPi
    ],
    extras_require={
        "web": ["microdot"],  # For MicrodotManager
    },
)