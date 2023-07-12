#!/usr/bin/python

import os
import sys
import re

from . exceptions import SymbioticExceptionalResult
from . options import SymbioticOptions
from . utils import dbg, print_elapsed_time, restart_counting_time
from . utils.process import ProcessRunner, runcmd
from . utils.watch import ProcessWatch, DbgWatch
from . utils.utils import print_stdout, print_stderr, process_grep
from . exceptions import SymbioticException
from shutil import move

class PrepareWatch(ProcessWatch):
    def __init__(self, lines=100):
        ProcessWatch.__init__(self, lines)

    def parse(self, line):
        if b'Removed' in line or b'Defining' in line:
            sys.stdout.write(line.decode('utf-8'))
        else:
            dbg(line.decode('utf-8'), 'prepare', False)


class SlicerWatch(ProcessWatch):
    def __init__(self, lines=100):
        ProcessWatch.__init__(self, lines)

    def parse(self, line):
        if b'ERROR' in line or b'error' in line:
            print_stderr(line.decode('utf-8'), print_nl=False)
        else:
            dbg(line.decode('utf-8'), 'slicer', print_nl = False,
                prefix='', color=None)


class InstrumentationWatch(ProcessWatch):
    def __init__(self, lines=100):
        ProcessWatch.__init__(self, lines)

    def parse(self, line):
        if b'Info' in line:
            dbg(line.decode('utf-8'), domain='instrumentation', print_nl=False,
                prefix='', color=None)
        elif b'ERROR' in line or b'error' in line:
            print_stderr(line.decode('utf-8'))
        elif b'Inserted' in line:
            print_stdout(line.decode('utf-8'), print_nl=False)
        else:
            dbg(line.decode('utf-8'), 'slicer', print_nl = False,
                prefix='', color=None)


class PrintWatch(ProcessWatch):
    def __init__(self, prefix='', color=None):
        ProcessWatch.__init__(self)
        self._prefix = prefix
        self._color = color

    def parse(self, line):
        print_stdout(line.decode('utf-8'), prefix=self._prefix,
                     print_nl=False, color=self._color)


class CompileWatch(ProcessWatch):
    """ Parse output of compilation """

    def __init__(self, nodbg = False):
        ProcessWatch.__init__(self)
        self.nodbg = nodbg

    def parse(self, line):
        if b'error:' in line:
            print_stderr('cc: {0}'.format(line.decode('utf-8')), color='BROWN')
        else:
            if not self.nodbg:
                dbg(line.decode('utf-8'), 'compile', print_nl=False)


class UnsuppWatch(ProcessWatch):
    unsupported_call = re.compile('.*call to .* is unsupported.*')

    def __init__(self):
        ProcessWatch.__init__(self)
        self._ok = True

    def ok(self):
        return self._ok

    def parse(self, line):
        uline = line.decode('utf-8')
        dbg(uline, domain='prepare', print_nl=False)
        self._ok = not UnsuppWatch.unsupported_call.match(uline)

def get_optlist_before(optlevel):
    from . optimizations import optimizations
    lst = []
    for opt in optlevel:
        if not opt.startswith('before-'):
            continue

        o = opt[7:]
        if o.startswith('opt-'):
            lst.append(o[3:])
        else:
            if o in optimizations:
                lst += optimizations[o]

    return lst

def get_optlist_after(optlevel):
    from . optimizations import optimizations
    lst = []
    for opt in optlevel:
        if not opt.startswith('after-'):
            continue

        o = opt[6:]
        if o.startswith('opt-'):
            lst.append(o[3:])
        else:
            if o in optimizations:
                lst += optimizations[o]

    return lst

class SymbioticCC(object):
    """
    Instance of symbiotic compiler tool.
    Instruments, prepares, and slices the program.
    """

    def __init__(self, src, tool, opts=None, env=None):
        # source file
        self.sources = src
        # source compiled to llvm bitecode
        self.curfile = None
        # environment
        self.env = env

        if opts is None:
            self.options = SymbioticOptions(env.symbiotic_dir)
        else:
            self.options = opts

        # definitions of our functions that we linked
        self._linked_functions = []

        # tool to use
        self._tool = tool

        # optimization renames in used LLVM release
        self._opt_renames = {}

    def _get_cc(self):
        if hasattr(self._tool, 'cc'):
            return self._tool.cc()

        return ['clang']

    def cc_has_lifetime_markers(self):
        retval, out = process_grep(self._get_cc() + ['-cc1', '--help'],
                                   '-fsanitize-address-use-after-scope')
        return retval == 0 and len(out) == 1 and\
                out[0].lstrip().decode('ascii').startswith('-fsanitize-address-use-after-scope')

    def cc_disable_optimizations(self):
        # Use -O0 -disable-O0-optnone to get the code without optnone attribute
        # so that it can get optimized later.
        # XXX: does -disable-llvm-passes have an effect here?
        return ['-O0', '-disable-O0-optnone', '-disable-llvm-passes']

    def _save_ll(self):
        """
        This is _generate_ll() that is enabled
        only when save_files is turned on (so that we do not
        generate .ll redundantly)
        """
        if not self.options.save_files:
            return
        return self._generate_ll()

    def _generate_ll(self, outf=None):
        if not self.options.generate_ll:
            return
        cmd = ["llvm-dis", self.curfile]
        if outf is not None:
            cmd += ['-o', outf]

        try:
            runcmd(cmd, CompileWatch(),
                    "Generating .ll file from '{0}' failed".format(self.curfile))
        except SymbioticException as e:
            dbg(str(e))
            dbg("This is a debugging feature, continuing...")

    def command(self, cmd):
        return runcmd(cmd, DbgWatch('all'),
                      "Failed running command: {0}".format(" ".join(cmd)))

    def _compile_to_llvm(self, source, output=None, with_g=True, opts=[]):
        """
        Compile given source to LLVM bitecode
        """

        # __inline attribute is buggy in clang, remove it using -D__inline
        cmd = self._get_cc() + ['-c', '-emit-llvm',
                                #'-include', 'symbiotic.h',
                                # otherwise clang can drop so inline functions
                                # e.g. push() in this file:
                                # https://github.com/sosy-lab/sv-benchmarks/blob/master/c/pthread-ext/36_stack_cas_p0_vs_concur.c
                                # it works also to compile with -O1 or -Og
                                '-fgnu89-inline',
                                '-D__inline='] + opts

        if with_g:
            cmd.append('-g')

        if self.options.CFLAGS:
            cmd += self.options.CFLAGS
        if self.options.CPPFLAGS:
            cmd += self.options.CPPFLAGS

        if self.options.is32bit:
            cmd.append('-m32')

        if self.options.generate_ll:
            # make the bitcode better readable if we generate the .ll files
            cmd.append("-fno-discard-value-names")

        cmd.append('-o')
        if output is None:
            basename = os.path.basename(source)
            llvmfile = '{0}.bc'.format(basename[:basename.rfind('.')])
        else:
            llvmfile = output
        cmd.append(llvmfile)
        cmd.append(source)

        runcmd(cmd, CompileWatch(),
               "Compiling source '{0}' failed".format(source))

        return llvmfile

    def run_opt(self, passes):
        if not passes:
            return

        self._run_opt(passes)

    def _run_opt(self, passes):
        output = '{0}-pr.bc'.format(self.curfile[:self.curfile.rfind('.')])
        cmd = ['opt', '-load', 'LLVMsbt.so',
               self.curfile, '-o', output] + passes
        self._disable_new_pm(cmd)

        runcmd(cmd, PrepareWatch(), 'Running opt failed')
        self.curfile = output
        self._save_ll()

    def _disable_new_pm(self, cmd):
        # disable new pass manager in LLVM 13+
        # TODO: support natively
        ver_major, *_ = self._tool.llvm_version().split('.')
        if int(ver_major) >= 13:
            cmd.append('-enable-new-pm=0')

    def _get_stats(self, prefix=''):
        if not self.options.stats:
            return

        cmd = ['opt', '-load', 'LLVMsbt.so', '-count-instr',
               '-o', '/dev/null', self.curfile]
        self._disable_new_pm(cmd)

        try:
            runcmd(cmd, PrintWatch('INFO: ' + prefix), 'Failed running opt')
        except SymbioticException:
            # not fatal, continue working
            dbg('Failed getting statistics')

    def _instrument(self):
        if not hasattr(self._tool, 'instrumentation_options'):
            return

        config_dir, config_file, definitions, shouldlink =\
            self._tool.instrumentation_options()

        # override the config file if desired
        if self.options.property.memsafety() and\
            self.options.memsafety_config_file:
            config_file = self.options.memsafety_config_file

        if config_file is None:
            return

        # if we have config_file, we must have definitions file
        assert definitions

        llvm_dir = 'llvm-{0}'.format(self._tool.llvm_version())
        if self.options.is32bit:
            libdir = os.path.join(self.env.symbiotic_dir, llvm_dir, 'lib32')
        else:
            libdir = os.path.join(self.env.symbiotic_dir, llvm_dir, 'lib')

        prefix = self.options.instrumentation_files_path

        definitionsbc = None
        config = os.path.join(prefix, config_dir, config_file)

        if not os.path.isfile(config):
            raise SymbioticException("Not a valid config file: '{0}'".format(config))
        # check whether we have this file precompiled
        # (this may be a distribution where we're trying to
        # avoid compilation of anything else than sources)
        precompiled_bc = '{0}/{1}.bc'.format(libdir,definitions[:-2])
        if os.path.isfile(precompiled_bc):
            definitionsbc = precompiled_bc
        else:
            definitions = os.path.join(prefix, config_dir, definitions)
            assert os.path.isfile(definitions)

        # module with defintions of instrumented functions
        if not definitionsbc:
            definitionsbc = os.path.abspath(self._compile_to_llvm(definitions,\
                 output=os.path.basename(definitions[:-2]+'.bc'),
                 with_g=False, opts=['-O3']))

        assert definitionsbc

        self._get_stats('Before instrumentation ')
        print_stdout('INFO: Starting instrumentation', color='WHITE')

        output = '{0}-inst.bc'.format(self.curfile[:self.curfile.rfind('.')])
        if self.options.instrumentation_timeout > 0:
            cmd = ['timeout', str(self.options.instrumentation_timeout)]
        else:
            cmd = []

        cmd += ['sbt-instr', config, self.curfile, definitionsbc, output]
        if not shouldlink:
            cmd.append('--no-linking')

        restart_counting_time()
        watch = InstrumentationWatch()

        process = ProcessRunner()
        retval = process.run(cmd, watch)
        if retval != 0:
            for line in watch.getLines():
                if b'PredatorPlugin: Predator found no errors' in line:
                    raise SymbioticExceptionalResult('true')

            for line in watch.getLines():
                print_stderr(line.decode('utf-8'),
                             color='RED', print_nl=False)
            # on timeout, just proceed, but avoid slicing and such,
            # since it depends on instrumentation
            if not self.options.full_instrumentation and\
                    (retval == 124 or self.options.sv_comp):
                self.options.noslice = True
                self.options.no_optimize = False
                self.options.optlevel = []
            else:
                raise SymbioticException('Instrumenting the code failed')
            print_elapsed_time('INFO: Instrumentation [FAILED] time', color='WHITE')
        else:
            print_elapsed_time('INFO: Instrumentation time', color='WHITE')
            self.curfile = output
            self._save_ll()

        self._get_stats('After instrumentation ')

    def instrument(self):
        """
        Instrument the code.
        """
        self._instrument()

    def link(self, libs, output=None):
        assert libs
        if output is None:
            output = '{0}-ln.bc'.format(
                self.curfile[:self.curfile.rfind('.')])

        cmd = ['llvm-link', '-o', output] + libs
        if self.curfile:
            cmd.append(self.curfile)

        runcmd(cmd, DbgWatch('compile'),
               'Failed linking llvm file with libraries')
        self.curfile = output
        self._save_ll()

    def _link_undefined(self, undefs):
        def _get_path(symbdir, llvmver, ty, tool, undef):
            # check also if we have precompiled .bc files
            if self.options.is32bit:
                path = os.path.abspath('{0}/llvm-{1}/lib32/{2}/{3}/{4}.bc'.format(symbdir, llvmver, ty, tool, undef))
            else:
                path = os.path.abspath('{0}/llvm-{1}/lib/{2}/{3}/{4}.bc'.format(symbdir, llvmver, ty, tool, undef))
            if os.path.isfile(path):
                return path

            path = os.path.abspath('{0}/lib/{1}/{2}/{3}.c'.format(symbdir, ty, tool, undef))
            if os.path.isfile(path):
                return path

            # do we have at least a generic implementation?
            if self.options.is32bit:
                path = os.path.abspath('{0}/llvm-{1}/lib32/{2}/{3}.bc'.format(symbdir, llvmver, ty, undef))
            else:
                path = os.path.abspath('{0}/llvm-{1}/lib/{2}/{3}.bc'.format(symbdir, llvmver, ty, undef))
            if os.path.isfile(path):
                return path

            path = os.path.abspath('{0}/lib/{1}/{2}.c'.format(symbdir, ty, undef))
            if os.path.isfile(path):
                return path

            return None

        def get_path(symbdir, llvmver, tool, undef):
            # return the first found definition (in the order of linkundef)
            for ty in self.options.linkundef:
                path = _get_path(symbdir, llvmver, ty, tool, undef)
                if path:
                    return path
            return None


        tolink = []
        for undef in undefs:
            path = get_path(self.env.symbiotic_dir, self._tool.llvm_version(),
                            self._tool.name().lower(), undef)
            if path is None:
                continue

            basename = os.path.basename(path)
            bcfile='{0}.bc'.format(basename[:basename.rfind('.')])
            output = os.path.abspath(bcfile)
            self._compile_to_llvm(path, output)
            tolink.append(output)

            # for debugging
            self._linked_functions.append(undef)

        if tolink:
            self.link(libs=tolink)
            return True

        return False

    def link_unconditional(self):
        """ Link the files that we got on the command line """

        return self._link_undefined(self.options.link_files)

    def _get_undefined(self, bitcode, only_func=None):
        cmd = ['llvm-nm', '-undefined-only', '-just-symbol-name', bitcode]
        watch = ProcessWatch(None)
        runcmd(cmd, watch, 'Failed getting undefined symbols from bitcode')
        undefs = list(map(lambda s: s.strip().decode('ascii'), watch.getLines()))
        if only_func:
            return [x for x in undefs if x in only_func]
        return undefs

    def _rec_link_undefined(self, only_func=None):
        # get undefined functions from the bitcode
        undefs = self._get_undefined(self.curfile, only_func)
        if self._link_undefined(undefs):
            # if we linked someting, try get undefined again,
            # because the functions may have added some new undefined
            # functions
            self._rec_link_undefined()

    def link_undefined(self, only_func=None):
        if not self.options.linkundef:
            return

        self._linked_functions = [] # for printing
        self._rec_link_undefined(only_func)

        if self._linked_functions:
            print('Linked our definitions to these undefined functions:')
            for f in self._linked_functions:
                print_stdout('  ', print_nl=False)
                print_stdout(f)

    def slicer(self, add_params=[]):
        if hasattr(self._tool, 'slicer_options'):
            crit, opts = self._tool.slicer_options()
        else:
            crit, opts = ['__assert_fail,__VERIFIER_error'], []

        assert len(crit) > 0

        output = '{0}.sliced'.format(self.curfile[:self.curfile.rfind('.')])


        if self.options.slicer_timeout > 0:
            cmd = ['timeout', str(self.options.slicer_timeout)] +\
                   self.options.slicer_cmd + ['-c', ",".join(crit)] + opts
        else:
            cmd = self.options.slicer_cmd + ['-c', ",".join(crit)] + opts

        if self.options.slicer_pta in ['fi', 'fs']:
            cmd.append('-pta')
            cmd.append(self.options.slicer_pta)

        # we do that now using _get_stats
        # cmd.append('-statistics')

        if self.options.undefined_are_pure:
            cmd.append('-undefined-are-pure')

        if self.options.slicer_params:
            cmd += self.options.slicer_params

        if add_params:
            cmd += add_params

        cmd.append(self.curfile)

        watch = SlicerWatch()
        process = ProcessRunner()
        retval = process.run(cmd, watch)
        if retval != 0:
            if retval != 124: # TIMEOUT of slicer
                for line in watch.getLines():
                    print_stderr(line.decode('utf-8'), color='RED', print_nl=False)
                print_stderr("INFO: Slicing FAILED, using the unsliced file.")
            else: # just keep the unsliced file
                print_stdout("INFO: Slicing timeouted, using the unsliced file.")
            if self.options.require_slicer:
                raise SymbioticException("Slicing failed (and is required)")

            # act as the slicing was disabled
            self.options.noslice = True
        else:
            self.curfile = output
            self._save_ll()

    def optimize(self, passes, disable=[], load_sbt = False):
        if not passes or self.options.no_optimize:
            return

        disable += self.options.disabled_optimizations
        if disable:
            passes = filter(lambda x: x not in disable, passes)

        if self._opt_renames:
            passes = map(lambda x: self._opt_renames.get(x, x), passes)

        if not passes:
            dbg("No passes available for optimizations")

        output = '{0}-opt.bc'.format(self.curfile[:self.curfile.rfind('.')])
        cmd = ['opt']
        if load_sbt:
            cmd += ['-load', 'LLVMsbt.so']
        self._disable_new_pm(cmd)
        cmd += ['-o', output, self.curfile]
        cmd += passes

        restart_counting_time()
        runcmd(cmd, CompileWatch(), 'Optimizing the code failed')
        print_elapsed_time('INFO: Optimizations time', color='WHITE')

        self.curfile = output
        self._save_ll()

    def _compile_sources(self, output='code.bc'):
        """
        Compile the given sources into LLVM bitcode and link them into one
        file named \param output. This output file is also set as the self.curfile.
        """

        opts = ['-Wno-unused-parameter', '-Wno-unknown-attributes',
                '-Wno-unused-label', '-Wno-unknown-pragmas',
                '-Wno-unused-command-line-argument']

        if self.options.property.memsafety():
            if self.cc_has_lifetime_markers():
                dbg('Clang supports lifetime markers, using it')
                opts.append('-Xclang')
                opts.append('-fsanitize-address-use-after-scope')
            else:
                print_stdout('Clang does not support lifetime markers, '
                             'scopes are not instrumented', color="BROWN")

        if hasattr(self._tool, 'compilation_options'):
            opts += self._tool.compilation_options()

        opts += self.cc_disable_optimizations()

        llvmsrc = []
        options = self.options
        for source in self.sources:
            if options.source_is_bc:
                dbg("Treating '{0}' as LLVM bitcode (required)".format(source))
                llvms = source
            elif source.endswith('.bc') or source.endswith('.ll'):
                dbg("Treating '{0}' as LLVM bitcode (according to suffix)".format(source))
                llvms = source
            else:
                llvms = self._compile_to_llvm(source, opts=opts)
            llvmsrc.append(llvms)

        # link all compiled sources to a one bitecode
        # the result is stored to self.curfile
        dbg("Linking all input files into one file")
        self.link(llvmsrc, output)

    def perform_slicing(self):
        self._get_stats('Before slicing ')

        add_params = []
        if hasattr(self._tool, 'slicing_params'):
            add_params += self._tool.slicing_params()

        print_stdout('INFO: Starting slicing', color='WHITE')
        restart_counting_time()
        for n in range(0, self.options.repeat_slicing):
            dbg('Slicing the code for the {0}. time'.format(n + 1))
            # if n == 0 and self.options.repeat_slicing > 1:
            #    add_params = ['-pta-field-sensitive=8']

            self.slicer(add_params)

            if self.options.repeat_slicing > 1:
                opt = get_optlist_after(self.options.optlevel)
                self.optimize(opt + ['-remove-infinite-loops'], load_sbt=True)

        print_elapsed_time('INFO: Total slicing time', color='WHITE')

        self._get_stats('After slicing ')

    def process_after_slicing(self):
        if hasattr(self._tool, 'actions_after_slicing'):
            self._tool.actions_after_slicing(self)

        passes = []

        # there may have been created new loops
        if not self.options.property.termination():
            passes.append('-remove-infinite-loops')

        # side-effects, because LLVM optimizations could remove them otherwise,
        # even though they contain calls to assert
        if self.options.property.memsafety():
            passes.append('-remove-readonly-attr')
            passes.append('-dummy-marker')

        if hasattr(self._tool, 'passes_after_slicing'):
            passes += self._tool.passes_after_slicing()
        self.run_opt(passes)

        # link undefined functions at this point
        self.link_undefined()

        # optimize the code after slicing and linking and before verification
        opt = get_optlist_after(self.options.optlevel)
        self.optimize(passes=opt)

        print_elapsed_time('INFO: After-slicing optimizations and transformations time',
                           color='WHITE')

    def prepare_unsliced_file(self, tool):
        """
        Get the unsliced file and perform the same
        postprocessing steps as for the sliced file
        """
        llvmfile = self.nonsliced_llvmfile
        tmp = self.curfile
        self.curfile = llvmfile

        self.process_after_slicing()

        llvmfile = self.curfile
        self.curfile = tmp

        return llvmfile


    def _disable_and_rename_optimizations(self, llvm_version):
        disabled = []
        # disable some oprimizations for termination property
        if self.options.property.termination():
            disabled += ['-functionattrs', '-instcombine']

        if self.options.property.signedoverflow():
            # FIXME: this is a hack, remove once we have better CD algorithm
            disabled += ['-instcombine']

        if self.options.property.memsafety():
            # these optimizations mess up with scopes,
            # FIXME: find a better solution
            disabled += ['-licm','-gvn','-early-cse']

        # disable optimizations that are not in particular llvm versions
        ver_major, ver_minor, ver_micro = map(int, llvm_version.split('.'))

        if ver_major == 3 and ver_minor <= 7:
            disabled += ['-aa', '-demanded-bits',
                        '-globals-aa', '-forceattrs',
                        '-inferattrs', '-rpo-functionattrs']
        if ver_major == 3 and ver_minor <= 6:
            disabled += ['-tti', '-bdce', '-elim-avail-extern',
                         '-float2int', '-loop-accesses']

        if disabled:
            dbg('Disabled these optimizations: %s' % disabled)
        self.options.disabled_optimizations = disabled

        renames = {}
        if ver_major >= 11:
            renames.update({'-basicaa': '-basic-aa'})

        if ver_major >= 12:
            renames.update({'-functionattrs': '-function-attrs',
                            '-rpo-functionattrs': '-rpo-function-attrs',
                            '-scoped-noalias': '-scoped-noalias-aa'})
        if renames:
            dbg('Renamed these optimizations: %s' % renames)
        self._opt_renames = renames

    def run(self):
        """
        Compile the program, optimize and slice it and
        return the name of the created bitcode
        """
        restart_counting_time()

        dbg('Running symbiotic-cc for {0}'.format(self._tool.name()))

        self._disable_and_rename_optimizations(self._tool.llvm_version())

        #################### #################### ###################
        # COMPILATION
        #  - compile the code into LLVM bitcode
        #################### #################### ###################

        # compile all given sources
        self._compile_sources()

        try:
            dbg("Searching for unsupported features in source file(s)...", color="BLUE")
            features = self._get_undefined(self.curfile)
            unsupported_features = [ "scanf", "abs", "fseek" ]
            dbg("Tested features: [ " + ", ".join(features) + " ]")
            dbg("Unsupported features: [ " + ", ".join(unsupported_features) + " ]")
            for feature in features:
                for unsupported in unsupported_features:
                    if unsupported in feature:
                        dbg("ERROR: Found '" + unsupported + "' in '" + feature + "'", color="RED")
                        return None
            dbg("No unsupported feature detected => proceeding to the analysis...", color="BLUE")
        except Exception as e:
            dbg("The search for unsupported features in source file(s) has FAILED: " + str(e), color="RED")

        # make the path absolute
        self.curfile = os.path.abspath(self.curfile)
        self._save_ll()

        self._get_stats('After compilation ')

        if hasattr(self._tool, 'passes_after_compilation'):
            self.run_opt(self._tool.passes_after_compilation())

        if hasattr(self._tool, 'actions_after_compilation'):
            self._tool.actions_after_compilation(self)

        # unroll the program if desired
        if self.options.unroll_count != 0:
            self.run_opt(['-reg2mem', '-sbt-loop-unroll',
                          '-sbt-loop-unroll-count',
                          str(self.options.unroll_count),
                          '-sbt-loop-unroll-terminate'])

        #################### #################### ###################
        # PREPROCESSING before instrumentation
        #  - prepare the code: remove calls to error functions if
        #    we do not aim for their reachability and link known
        #    functions that should be unconditionally linked to the
        #    module
        #################### #################### ###################

        # link the files that we got on the command line
        # and that we are required to link in on any circumstances
        self.link_unconditional()

        passes = []
        # NOTE: remove error calls must go first as the other passes
        # may include error calss
        prp = self.options.property
        if prp.memsafety() or \
           prp.undefinedness() or \
           prp.signedoverflow() or \
           prp.termination() or \
           prp.memcleanup():
            # remove the original calls to __VERIFIER_error/__assert_fail
            passes.append('-remove-error-calls')

        if prp.memcleanup() or prp.termination():
            passes.append('-remove-error-calls-use-exit')

        if not prp.termination():
            passes.append('-remove-infinite-loops')

        if prp.undefinedness() or \
           prp.signedoverflow():
            passes.append('-replace-ubsan')

        if prp.signedoverflow() and \
           not self.options.overflow_with_clang:
            passes.append('-replace-ubsan-just-remove')
            passes.append('-replace-ubsan-keep-shifts')
            passes.append('-prepare-overflows')
            passes.append('-mem2reg')
            passes.append('-break-crit-edges')

        self.run_opt(passes)

        #################### #################### ###################
        # INSTRUMENTATION
        #  - now instrument the code according to the given property
        #################### #################### ###################

        if not self.options.no_instrument:
            self.instrument()


        #################### #################### ###################
        # POSTPROCESSING after instrumentation
        #  - link functions to the instrumented module
        #################### #################### ###################

        passes = []
        if hasattr(self._tool, 'passes_after_instrumentation'):
            passes = self._tool.passes_after_instrumentation()

        if self.options.property.memsafety():
            # replace llvm.lifetime.start/end with __VERIFIER_scope_enter/leave
            # so that optimizations will not mess the code up
            passes.append('-replace-lifetime-markers')

            # make all store/load insts that are marked by instrumentation
            # volatile, so that we can run optimizations later on them
            passes.append('-mark-volatile')

        if passes:
            self.run_opt(passes)

        #################### #################### ###################
        # SLICING
        #  - slice the code w.r.t error sites
        #################### #################### ###################

        # run optimizations if desired
        passes = get_optlist_before(self.options.optlevel)
        # Special optimizations for slicing.
        if not self.options.noslice and 'before-O3' in self.options.optlevel:
            # Break the infinite loops just before slicing so that the
            # optimizations won't make them syntactically infinite again. We must
            # run reg2mem before breaking to loops, because breaking the loops can
            # not handle PHI nodes well.
            if self.options.property.termination():
                passes += ['-reg2mem', '-break-infinite-loops',]
            passes += ['-remove-infinite-loops',
                       '-mem2reg', '-break-crit-loops', '-lowerswitch']
        self.optimize(passes, load_sbt=True)

        if hasattr(self._tool, 'actions_before_slicing'):
            self._tool.actions_before_slicing(self)

        if self.options.link_files_before_slicing:
            self.link_undefined(self.options.link_files_before_slicing)

        # remember the non-sliced llvmfile
        self.nonsliced_llvmfile = self.curfile

        if hasattr(self._tool, 'passes_before_slicing'):
            passes = self._tool.passes_before_slicing()
            if passes:
                self.run_opt(passes)

        # link definition of atexit and get rid of llvm.global_dtors,
        # link also qsort before slicing as it can call function pointers
        self.link_undefined(['atexit', 'qsort'])
        self.run_opt(['-explicit-consdes'])

        if not self.options.noslice:
            self.perform_slicing()
        elif self.options.require_slicer:
            raise SymbioticException("Slicing required but forbiden...")

        # start a new time era
        restart_counting_time()

        self.process_after_slicing()

        self._get_stats('After slicing and post-processing')

        if not self.options.final_output is None:
            # copy the file to final_output
            try:
                dbg("Renaming the final file from '{0}' to '{1}'"\
                    .format(self.curfile, self.options.final_output))
                if self.options.generate_ll and\
                    self.options.final_output.endswith('.ll'):
                    self._generate_ll(self.options.final_output)
                else:
                    move(self.curfile, self.options.final_output)
                    self.curfile = self.options.final_output
                    self._generate_ll()
            except OSError as e:
                msg = 'Cannot create {0}: {1}'.format(
                    self.options.final_output, str(e))
                raise SymbioticException(msg)

        return self.curfile

