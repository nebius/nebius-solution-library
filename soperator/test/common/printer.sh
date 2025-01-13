#!/bin/bash

h1() { echo -e "$(tput setaf 12)$(tput bold)# ${1} $(tput sgr0)"; }
h2() { echo -e "$(tput setaf 13) ## ${1} $(tput sgr0)"; }
h3() { echo -e "$(tput setaf 6)  ### ${1} $(tput sgr0)"; }
hdone() { echo -e "$(tput setab 2)$(tput bold) V $(tput sgr0)$(tput setaf 10)$(tput bold) Done $(tput sgr0)"; }
herror() { echo -e "$(tput setab 1)$(tput bold) X $(tput sgr0)$(tput setaf 9)$(tput bold) ERROR$(tput sgr0): ${1}"; }
