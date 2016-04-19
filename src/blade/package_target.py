# Copyright (c) 2016 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   April 18, 2016

"""

This is the package target module which packages files
into an (compressed) archive.

"""

import os

import blade
import build_rules
import console
from blade_util import var_to_list
from blade_util import location_re
from target import Target


_package_types = frozenset([
    'tar',
    'tar.gz',
    'tgz',
    'tar.bz2',
    'tbz',
])


class PackageTarget(Target):
    """

    This class is derived from Target and used to generate scons
    rules for packaging files into an archive which could be 
    compressed using gzip or bz2 according to the package type.

    """
    def __init__(self,
                 name,
                 srcs,
                 deps,
                 type,
                 blade,
                 kwargs):
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)

        Target.__init__(self,
                        name,
                        'package',
                        [],
                        deps,
                        blade,
                        kwargs)

        if type not in _package_types:
            console.error_exit('%s: Invalid type %s. Types supported '
                               'by the package are %s' % (
                               self.fullname, type, ', '.join(sorted(_package_types))))
        self.data['type'] = type
        self.data['sources'], self.data['locations'] = [], []
        self._process_srcs(srcs)

    def _process_srcs(self, srcs):
        """
        Process sources which could be regular files, directories or
        location references.
        """
        for s in srcs:
            if isinstance(s, tuple):
                src, dst = s
            elif isinstance(s, str):
                src, dst = s, ''
            else:
                console.error_exit('%s: Invalid src %s. src should '
                                   'be either str or tuple.' % (self.fullname, s))

            m = location_re.search(src)
            if m:
                self._add_location_reference(m, dst)
            else:
                self._add_package_source(src, dst)

    def _add_location_reference(self, m, dst):
        """Add target location reference. """
        key, type = m.groups()
        if not type:
            type = ''
        type = type.strip()
        key = self._unify_dep(key)
        self.data['locations'].append((key, type, dst))
        if key not in self.expanded_deps:
            self.expanded_deps.append(key)
        if key not in self.deps:
            self.deps.append(key)

    def _get_source_path(self, src, dst):
        """
        Return src full path within the workspace and mapping path in the archive.
        """
        if '..' in src or '..' in dst:
            console.error_exit('%s: Invalid src (%s, %s). Relative path is not allowed.'
                               % (self.fullname, src, dst))
        elif src.startswith('//'):
            src = src[2:]
            path = src
        else:
            path = self._source_file_path(src)
        
        if not dst:
            dst = src
        return path, dst

    def _add_package_source(self, src, dst):
        """Add regular file or directory. """
        src, dst = self._get_source_path(src, dst)
        if os.path.isfile(src):
            self.data['sources'].append((src, dst))
        else:
            for dir, subdirs, files in os.walk(src):
                for f in files:
                    f = os.path.join(dir, f)
                    rel_path = os.path.relpath(f, src)
                    self.data['sources'].append((f, os.path.join(dst, rel_path)))

    def _generate_source_rules(self, source_vars, package_path_list, sources_dir):
        env_name = self._env_name()
        for i, source in enumerate(self.data['sources']):
            src, dst = source[0], os.path.join(sources_dir, source[1])
            var = self._var_name('source__%s' % i)
            self._write_rule('%s = %s.PackageSource(target = "%s", source = "%s")' %
                             (var, env_name, dst, src))
            source_vars.append(var)
            package_path_list.append(dst)

    def _generate_location_reference_rules(self, location_vars,
                                           package_path_list, sources_dir):
        env_name = self._env_name()
        targets = self.blade.get_build_targets()
        for i, location in enumerate(self.data['locations']):
            key, type, dst = location
            target = targets[key]
            target_var = target._get_target_var(type)
            if not target_var:
                console.warning('%s: Location %s %s is missing. Ignored.' %
                                (self.fullname, key, type))
                continue

            if dst:
                dst = os.path.join(sources_dir, dst)
                var = self._var_name('location__%s' % i)
                self._write_rule('%s = %s.PackageSource(target = "%s", source = %s)' %
                                 (var, env_name, dst, target_var))
                location_vars.append(var)
                package_path_list.append(dst)
            else:
                location_vars.append(target_var)

    def scons_rules(self):
        """scons_rules. """
        self._clone_env()
        env_name = self._env_name()
        var_name = self._var_name()

        source_vars, location_vars, package_path_list = [], [], []
        sources_dir = self._target_file_path() + '.sources'
        package_type = self.data['type']
        self._generate_source_rules(source_vars, package_path_list, sources_dir)
        self._generate_location_reference_rules(location_vars,
                                                package_path_list, sources_dir)
        self._write_rule('%s = %s.Package(target="%s.%s", source=[%s] + [%s])' % (
                         var_name, env_name,
                         self._target_file_path(), package_type,
                         ','.join(source_vars), ','.join(location_vars)))
        self._write_rule('%s.Append(PACKAGESUFFIX="%s")' % (env_name, package_type))
        if package_path_list:
            self._write_rule('%s.Depends(%s, %s.Value(%s))' % (
                env_name, var_name, env_name, package_path_list))


def package(name,
            srcs,
            deps=[],
            type='tar',
            **kwargs):
    package_target = PackageTarget(name,
                                   srcs,
                                   deps,
                                   type,
                                   blade.blade,
                                   kwargs)
    blade.blade.register_target(package_target)


build_rules.register_function(package)
