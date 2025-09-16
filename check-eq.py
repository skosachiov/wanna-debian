#
# grep-dctrl -P -e "" -s Package,Version,Depends trixie_Packages | awk 'BEGIN {ORS=RS="\n\n"} {gsub(/\n/, " "); print}' | grep --color -P " \(=" > /tmp/check-eq.list
#
import re

with open('/tmp/check-eq.list', 'r') as file:
    for line in file:
        versions = re.findall(r'\(= ([^)]+)\)', line)
        for version in versions:
            if f'Version: {version}' not in line:
                print(line.strip())

