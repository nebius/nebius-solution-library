#!/bin/bash

h1() { echo -e "$(tput setab 12)$(tput setaf 0)$(tput bold) ${1} $(tput sgr0)"; }
h2() { echo -e "$(tput setab 14)$(tput setaf 0)   ${1} $(tput sgr0)"; }
hdone() { echo -e "$(tput setab 10)$(tput setaf 0)   Done $(tput sgr0)"; }
herror() { echo -e "$(tput setab 1)$(tput bold) ERROR: ${1} $(tput sgr0)"; }
