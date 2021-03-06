import glob
import os
import re
import sys
from collections import defaultdict
from subprocess import check_output, CalledProcessError

from jinja2 import Environment, PackageLoader

from s3pypi import __prog__
from s3pypi.exceptions import S3PyPiError

__author__ = 'Matteo De Wint'
__copyright__ = 'Copyright 2016, November Five'
__license__ = 'MIT'

log = logging.getLogger()


class Package(object):
    """Python package."""

    def __init__(self, name, files):
        self.name, self.version = name.rsplit('-', 1)
        self.files = set(files)

    def __str__(self):
        return '%s-%s' % (self.name, self.version)

    def _attrs(self):
        return self.name, self.version

    def __lt__(self, other):
        return self.version < other.version

    def __eq__(self, other):
        return isinstance(other, Package) and self._attrs() == other._attrs()

    def __hash__(self):
        return hash(self._attrs())

    @property
    def directory(self):
        return re.sub('[-_.]+', '-', self.name)

    @staticmethod
    def _find_package_name(text):
        match = re.search('^(copying files to|making hard links in) (.+)\.\.\.', text, flags=re.MULTILINE)

        if not match:
            raise RuntimeError('Package name not found! (use --verbose to view output)')

        return match.group(2)

    @staticmethod
    def _find_wheel_name(text):
        match = re.search("creating '.*(dist.*\.whl)' and adding", text, flags=re.MULTILINE)

        if not match:
            raise RuntimeError('Wheel name not found! (use --verbose to view output)')

        return match.group(1)

    @staticmethod
    def create(wheel=True, sdist=True):
        cmd = [sys.executable, 'setup.py', 'sdist', '--formats', 'gztar']

        if wheel:
            cmd.append('bdist_wheel')

        log.debug("Package create command line: {}".format(' '.join(cmd)))
            
        try:
            stdout = check_output(cmd).decode().strip()
        except CalledProcessError as e:
            raise RuntimeError(e.output.rstrip())

        log.debug(stdout)
            
        name = Package._find_package_name(stdout)
        files = []

        if sdist:
            files.append(name + '.tar.gz')

        if wheel:
            files.append(os.path.basename(Package._find_wheel_name(stdout)))

        log.debug("Package name: {}".format(name))
        log.debug("Files to upload: {}".format(files))
            
        return Package(name, files)


class Index(object):
    """Index of package versions, to be rendered to HTML."""

    template = Environment(loader=PackageLoader(__prog__, 'templates')).get_template('index.html.j2')

    def __init__(self, packages):
        self.packages = set(packages)

    @staticmethod
    def parse(html):
        filenames = defaultdict(set)

        for match in re.findall('<a href="((.+?-\d+\.\d+\.\d+).+)">', html):
            filenames[match[1]].add(match[0])

        return Index(Package(name, files) for name, files in filenames.items())

    def to_html(self):
        return self.template.render({'packages': self.packages})

    def add_package(self, package, force=False):
        if force:
            self.packages.discard(package)
        elif any(p.version == package.version for p in self.packages):
            raise S3PyPiError('%s already exists! You should use a different version (use --force to override).' % package)

        self.packages.add(package)
