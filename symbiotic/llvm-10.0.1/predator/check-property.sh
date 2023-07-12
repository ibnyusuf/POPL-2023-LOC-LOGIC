#!/bin/bash
export SELF="$0"
export LC_ALL=C
export CCACHE_DISABLE=1

export MSG_INFLOOP=': warning: end of function .*\(\) has not been reached'
export MSG_LABEL_FOUND=': error: error label "ERROR" has been reached'
export MSG_LABEL_UNREACHABLE=': warning: unreachable label .*'
export MSG_VERIFIER_ERROR_FOUND=': (error|warning): __VERIFIER_error\(\) reached'
export MSG_OUR_WARNINGS=': warning: .*(\[-fplugin=libsl.so\]|\[-sl\])$'
export MSG_TIME_ELAPSED=': note: clEasyRun\(\) took '
export MSG_INTERVAL_REDUCE=': warning: reduce .*er bound of half-open interval'
export MSG_UNHANDLED_CALL=': warning: ignoring call of undefined function: '
export MSG_INT_OVERFLOW=': warning: possible .*flow of .* integer'
export MSG_COND_JUMP_UNINIT_VALUE=': warning: conditional jump depends on uninitialized value'

export MSG_MEMLEAK=': (error|warning): memory leak detected'

export MSG_DEREF_FREED=': error: dereference of already deleted heap object'
export MSG_DEREF_OUT=': error: dereferencing object of size [0-9]*B out of bounds'
export MSG_DEREF_NULL=': error: dereference of NULL value'
export MSG_DEREF_INVALID=': error: invalid dereference'
export MSG_DEREF_NENH=': error: dereference of non-existing non-heap object'
export MSG_DEREF_PTRSPACE=": error: not enough space to store value of a pointer"
export MSG_DEREF_LVAL=": error: invalid L-value"

export MSG_FREE_OFFSET=': error: (free|realloc)\(\) called with offset'
export MSG_FREE_INVALID=': error: invalid free\(\)'
export MSG_FREE_DOUBLE=': error: double free'
export MSG_FREE_NENH=': error: attempt to free a non-existing non-heap object'
export MSG_FREE_NONHEAP=': error: attempt to free a non-heap object'
export MSG_FREE_NONPOINTER=': error: (free|realloc)\(\) called on non-pointer value'

# Predator error messages we need to handle:
#"invalid realloc()"
#"new_size arg of realloc() is not a known integer" - probably not
#"size arg of memset() is not a known integer" - no category
#"size arg of " << fnc << " is not a known integer" - probably not
#"source and destination overlap in call of " - not category
#"internal error in valMerge(), heap inconsistent!" - probably not
#"'nelem' arg of calloc() is not a known integer" - probably not
#"'elsize' arg of calloc() is not a known integer" - probably not
#"failed to imply a zero-terminated string" - probably not
#"size arg of " << name << "() is not a known integer"- probably not
#"size arg of malloc() is not a known integer" - probably not
#"fmt arg of printf() is not a string literal" - probably not
#"insufficient count of arguments given to printf()" - probably not
#"unhandled conversion given to printf()" - probably not
#"n arg of " << name << "() is not a known integer" - probably not
#"call cache entry found, but result not " - probably not
#"call cache entry found, but result not " - probably not
#": " << "entry block not found" - probably not
#"failed to resolve indirect function call" - probably not
#"call depth exceeds SE_MAX_CALL_DEPTH" - probably not

# Predator warnings we need to handle
#"ignoring call of memset() with size == 0" - not
#"ignoring call of " << fnc << " with size == 0" - not
#"incorrectly called " - not
#"() failed to read node_name" - not
#"error while plotting '" << plotName << "'" - not
#"() reached, stopping per user's request" - not
#"too many arguments given to printf()" - not
#"error while plotting '" << plotName << "'" - not
#"end of function " - not
#"caught signal " - not

usage() {
    printf "Usage: %s --propertyfile FILE [--trace FILE] -- path/to/test-case.c \
[-m32|-m64] [CFLAGS]\n\n" "$SELF" >&2
    cat >&2 << EOF

    -p, --propertyfile FILE
          A file specifying the verification property.  See the competition
          rules for details: http://sv-comp.sosy-lab.org/2014/rules.php

    -t, --trace FILE
          A file name to write the trace to.

    -x, --xmltrace FILE
          A file name to write the XML trace to. (Default: no XML trace)
          Warning: no colon and no whitespace in FILE allowed

    -d, --depth NUMBER
          A depth limit. (Default: unlimited)

    -v, --verbose
          Prints more information about the result. Not to be used during the
          competition.

    The verification result (TRUE, FALSE, or UNKNOWN) will be printed to
    standard output.  All other information will be printed to standard error
    output (or the file specified by the --trace option).  There is no timeout
    or ulimit set by this script.  If these constraints are violated, it should
    be treated as UNKNOWN result.  Do not forget to use the -m32 option when
    compiling 32bit preprocessed code on a 64bit OS.

    For memory safety category, the FALSE result is further clarified as
    FALSE(p) where p is the property for which the Predator judges the
    program to be unsatisfactory.
EOF
    exit 1
}

PRP_FILE=
DEPTH=""
XMLTRACE=""
SRC_FILE=
ARCH=

# write trace to stderr by default
TRACE="/dev/fd/2"

ARGS=$(getopt -o p:t:x:d:v -l "propertyfile:,trace:,xmltrace:,depth:,verbose" -n "$SELF" -- "$@")
if test $? -ne 0; then
  usage; exit 1;
fi

eval set -- $ARGS

while [ $# -gt 0 ]; do
  case "$1" in
    -p|--propertyfile)
      PRP_FILE="$2"; shift 2;;
    -t|--trace)
      TRACE="$2"; shift 2;;
    -x|--xmltrace)
      XMLTRACE="$2"; shift 2;;
    -d|--depth)
      DEPTH="$2"; shift 2;;
    -v|--verbose)
      export VERBOSE="yes"; shift;;
    --)
      SRC_FILE="$2"; shift 2; CFLAGS="$@";;
    -m32)
      ARCH="32"; break;;
    -m64)
      ARCH="64"; break;;
    *)
      shift;;
  esac
done

test -r "$SRC_FILE" || usage
test -r "$PRP_FILE" || usage

# classify the property to be verified
TASK=""
if grep "call(__VERIFIER_error()" "$PRP_FILE" >/dev/null; then
    TASK="$TASK VERIFIER_error"
fi; if grep "valid-memcleanup" "$PRP_FILE" >/dev/null; then
    TASK="$TASK memcleanup"
fi; if grep "valid-memtrack" "$PRP_FILE" >/dev/null; then
    TASK="$TASK memtrack"
fi; if grep "valid-deref" "$PRP_FILE" >/dev/null; then
    TASK="$TASK deref"
fi; if grep "valid-free" "$PRP_FILE" >/dev/null; then
    TASK="$TASK free"
fi; if grep "! overflow" "$PRP_FILE" >/dev/null; then
    TASK="$TASK overflow"
fi; if [ -z "$TASK" ]; then
    printf "%s: error: failed to classify any properties to verify: %s\n" \
        "$SELF" "$PRP_FILE" >&2
    exit 1
fi

# basic setup
# include common code base
topdir="`dirname "$(readlink -f "$SELF")"`/.."
source "$topdir/build-aux/xgcclib.sh" # defines find_*() and die() functions (NOT needed for sv-comp)
# basic setup & initial checks
export SL_PLUG='/home/marek/root/DOCKER_SVCOMP/symbiotic/predator-10.0.1/sl_build/libsl.so'
export ENABLE_LLVM='ON'
if [ -z $ENABLE_LLVM ]; then
    export GCC_HOST=''
    find_gcc_host
else
    export PASSES_LIB='/home/marek/root/DOCKER_SVCOMP/symbiotic/predator-10.0.1/sl/../passes-src/passes_build/libpasses.so'
    export OPT_HOST='/home/marek/root/DOCKER_SVCOMP/symbiotic/llvm-10.0.1/build/bin/opt'
    export CLANG_HOST='/home/marek/root/DOCKER_SVCOMP/symbiotic/llvm-10.0.1/build/bin/clang'
    find_clang_host
    find_opt_host
    find_plug PASSES_LIB passes Passes
fi

#export GCC_PLUG=''
export GCC_PLUG="$topdir/sl_build/libsl.so"
export GCC_HOST=''

## initial checks (NOT needed for sv-comp)
#find_gcc_host
#find_gcc_plug sl Predator

match() {
    line="$1"
    shift
    [[ $line =~ $@ ]]
    return $?
}

report_result() {
    if test -n "$VERBOSE"; then
      printf "$1$2: $3\n"
    else
      printf "$1$2\n"
    fi
}

fail() {
    # exit now, it makes no sense to continue at this point
    report_result "UNKNOWN" "" "$1"
    exit 1
}

report_unsafe() {
    if test xyes = "x$OVERAPPROX"; then
        fail "warning: maybe false alarm"
    fi

    PROPERTY="$1"

    # drop the remainder of the output
    cat > /dev/null
    if test -z "$PROPERTY"; then
      # set property in XML trace
      SPEC=`cat "$PRP_FILE"`
      report_result "FALSE" "" "$2"
    else
      # set property in XML trace
      SPEC=`grep $PROPERTY $PRP_FILE`
      report_result "FALSE" "($PROPERTY)" "$2"
    fi

    # change witness XML
    HASH=`(sha1sum "$SRC_FILE" | sed 's/ .*//')`

    if test -z "$HASH"; then
      printf "%s: error: failed to generate hash for: %s\n" "$SELF" \
        "$SRC_FILE" >&2
    fi

    if test -z "$SPEC"; then
      printf "%s: error: failed to generate specification from: %s\n" "$SELF" \
        "$PRP_FILE" >&2
    fi

    if test -n "$XMLTRACE"; then
      sed -i '' s/__SRCFILEHASH__/"${HASH}"/ "$XMLTRACE"
      sed -i '' s/__SPECIFICATION__/"${SPEC}"/ "$XMLTRACE"
      sed -i '' s/__ARCHITECTURE__/"${ARCH}bit"/ "$XMLTRACE"
    fi

    exit 0
}

report_safe() {
#    PROPERTY="$1"

    report_result "TRUE" "" "$2"
    # generate correctness witness with all properties
    SPEC=`cat "$PRP_FILE"`
    HASH=`(sha1sum "$SRC_FILE" | sed 's/ .*//')`

    if test -z "$HASH"; then
      printf "%s: error: failed to generate hash for: %s\n" "$SELF" \
        "$SRC_FILE" >&2
    fi

    if test -z "$SPEC"; then
      printf "%s: error: failed to generate specification from: %s\n" "$SELF" \
        "$PRP_FILE" >&2
    fi

    # graph with one start node
    if test -n "$XMLTRACE"; then
    echo -e "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"no\"?>\n\
<graphml xmlns=\"http://graphml.graphdrawing.org/xmlns\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">\n\
\t<key attr.name=\"originFileName\" attr.type=\"string\" for=\"edge\" id=\"originfile\">\n\
\t\t<default>\"&lt;command-line&gt;\"</default>\n\
\t</key>\n\
\t<key attr.name=\"invariant\" attr.type=\"string\" for=\"node\" id=\"invariant\"/>\n\
\t<key attr.name=\"invariant.scope\" attr.type=\"string\" for=\"node\" id=\"invariant.scope\"/>\n\
\t<key attr.name=\"namedValue\" attr.type=\"string\" for=\"node\" id=\"named\"/>\n\
\t<key attr.name=\"nodeType\" attr.type=\"string\" for=\"node\" id=\"nodetype\">\n\
\t\t<default>path</default>\n\
\t</key>\n\
\t<key attr.name=\"isFrontierNode\" attr.type=\"boolean\" for=\"node\" id=\"frontier\">\n\
\t\t<default>false</default>\n\
\t</key>\n\
\t<key attr.name=\"isViolationNode\" attr.type=\"boolean\" for=\"node\" id=\"violation\">\n\
\t\t<default>false</default>\n\
\t</key>\n\
\t<key attr.name=\"isEntryNode\" attr.type=\"boolean\" for=\"node\" id=\"entry\">\n\
\t\t<default>false</default>\n\
\t</key>\n\
\t<key attr.name=\"isSinkNode\" attr.type=\"boolean\" for=\"node\" id=\"sink\">\n\
\t\t<default>false</default>\n\
\t</key>\n\
\t<key attr.name=\"enterLoopHead\" attr.type=\"boolean\" for=\"edge\" id=\"enterLoopHead\">\n\
\t\t<default>false</default>\n\
\t</key>\n\
\t<key attr.name=\"violatedProperty\" attr.type=\"string\" for=\"node\" id=\"violatedProperty\"/>\n\
\t<key attr.name=\"threadId\" attr.type=\"string\" for=\"edge\" id=\"threadId\"/>\n\
\t<key attr.name=\"sourcecodeLanguage\" attr.type=\"string\" for=\"graph\" id=\"sourcecodelang\"/>\n\
\t<key attr.name=\"programFile\" attr.type=\"string\" for=\"graph\" id=\"programfile\"/>\n\
\t<key attr.name=\"programHash\" attr.type=\"string\" for=\"graph\" id=\"programhash\"/>\n\
\t<key attr.name=\"specification\" attr.type=\"string\" for=\"graph\" id=\"specification\"/>\n\
\t<key attr.name=\"memoryModel\" attr.type=\"string\" for=\"graph\" id=\"memorymodel\"/>\n\
\t<key attr.name=\"architecture\" attr.type=\"string\" for=\"graph\" id=\"architecture\"/>\n\
\t<key attr.name=\"producer\" attr.type=\"string\" for=\"graph\" id=\"producer\"/>\n\
\t<key attr.name=\"sourcecode\" attr.type=\"string\" for=\"edge\" id=\"sourcecode\"/>\n\
\t<key attr.name=\"startline\" attr.type=\"int\" for=\"edge\" id=\"startline\"/>\n\
\t<key attr.name=\"startoffset\" attr.type=\"int\" for=\"edge\" id=\"startoffset\"/>\n\
\t<key attr.name=\"lineColSet\" attr.type=\"string\" for=\"edge\" id=\"lineCols\"/>\n\
\t<key attr.name=\"control\" attr.type=\"string\" for=\"edge\" id=\"control\"/>\n\
\t<key attr.name=\"assumption\" attr.type=\"string\" for=\"edge\" id=\"assumption\"/>\n\
\t<key attr.name=\"assumption.resultfunction\" attr.type=\"string\" for=\"edge\" id=\"assumption.resultfunction\"/>\n\
\t<key attr.name=\"assumption.scope\" attr.type=\"string\" for=\"edge\" id=\"assumption.scope\"/>\n\
\t<key attr.name=\"enterFunction\" attr.type=\"string\" for=\"edge\" id=\"enterFunction\"/>\n\
\t<key attr.name=\"returnFromFunction\" attr.type=\"string\" for=\"edge\" id=\"returnFrom\"/>\n\
\t<key attr.name=\"predecessor\" attr.type=\"string\" for=\"edge\" id=\"predecessor\"/>\n\
\t<key attr.name=\"successor\" attr.type=\"string\" for=\"edge\" id=\"successor\"/>\n\
\t<key attr.name=\"witness-type\" attr.type=\"string\" for=\"graph\" id=\"witness-type\"/>\n\
\n\
<graph edgedefault=\"directed\">\n\
\t<data key=\"sourcecodelang\">C</data>\n\
\t<data key=\"producer\">PredatorHP</data>\n\
\t<data key=\"specification\">${SPEC}</data>\n\
\t<data key=\"programhash\">${HASH}</data>\n\
\t<data key=\"memorymodel\">precise</data>\n\
\t<data key=\"architecture\">${ARCH}bit</data>\n\
\t<data key=\"programfile\">${SRC_FILE}</data>\n\
\t<data key=\"witness-type\">correctness_witness</data>\n\
\t<node id=\"A1\">\n\
\t\t<data key=\"entry\">true</data>\n\
\t</node>\n\
</graph>\n\
</graphml>" > "$XMLTRACE"
    fi

    exit 0
}

parse_output() {
    ERROR_DETECTED=no
    ENDED_GRACEFULLY=no

    while read line; do
        if match "$line" "$MSG_UNHANDLED_CALL"; then
            # call of an external function we have no model for, we have to fail
            fail "$line"

        elif match "$line" "$MSG_COND_JUMP_UNINIT_VALUE"; then
            # on purpose for ldv-memsafety/memleaks_test12_
            # conditional jump depends on uninitialized value
            fail "$line"

        elif match "$line" "$MSG_INT_OVERFLOW"; then
            # unhandled integer overflow, we have to fail
            if match "$TASK" "overflow"; then
              report_unsafe "" "$line"
            else
              fail "$line"
            fi

        elif match "$line" "$MSG_VERIFIER_ERROR_FOUND"; then
            # an __VERIFIER_error() has been reached
            if match "$TASK" "VERIFIER_error"; then
              report_unsafe "" "$line"
            fi

        #elif match "$line" "$MSG_LABEL_FOUND"; then
        #    # an ERROR label has been reached
        #    if match "$TASK" "VERIFIER_error"; then
        #      report_unsafe "" "$line"
        #    fi

        elif match "$line" "$MSG_DEREF_FREED" || \
             match "$line" "$MSG_DEREF_OUT" || \
             match "$line" "$MSG_DEREF_NULL" || \
             match "$line" "$MSG_DEREF_INVALID" || \
             match "$line" "$MSG_DEREF_NENH" || \
             match "$line" "$MSG_DEREF_PTRSPACE" || \
             match "$line" "$MSG_DEREF_LVAL" ; then
            if match "$TASK" "deref"; then
              report_unsafe "valid-deref" "$line"
            fi

        elif match "$line" "$MSG_MEMLEAK"; then
            if match "$TASK" "memtrack"; then
              report_unsafe "valid-memtrack" "$line"
            elif match "$TASK" "memcleanup"; then
              report_unsafe "valid-memcleanup" "$line"
            fi

        elif match "$line" "$MSG_FREE_OFFSET" || \
             match "$line" "$MSG_FREE_INVALID" || \
             match "$line" "$MSG_FREE_DOUBLE" || \
             match "$line" "$MSG_FREE_NENH" || \
             match "$line" "$MSG_FREE_NONHEAP" || \
             match "$line" "$MSG_FREE_NONPOINTER"; then
            # free called with offset: valid_free
            if match "$TASK" "free"; then
              report_unsafe "valid-free" "$line"
            fi

        elif match "$line" ": error: "; then
            # errors already reported, better to fail now
            fail "$line"

        elif match "$line" "$MSG_INFLOOP" || \
             match "$line" "$MSG_LABEL_UNREACHABLE" || \
             match "$line" "$MSG_INTERVAL_REDUCE"; then
            # infinite loop does not mean FALSE
            # interval reduce only for huters too, ignore them
            continue #why continue in elif?

        elif match "$line" "$MSG_OUR_WARNINGS"; then
            # all other warnings treat as errors
            ERROR_DETECTED=yes

        elif match "$line" "$MSG_TIME_ELAPSED"; then
            # we ended up without a crash, yay!
            ENDED_GRACEFULLY=yes

        fi
    done

    if test xyes = "x$ERROR_DETECTED"; then
        fail "warning: Encountered some warnings"
    elif test xyes = "x$ENDED_GRACEFULLY"; then
        report_safe "$TASK" "$line"
    else
        fail "error: Predator has not finished gracefully"
    fi
}

if match "$TASK" "VERIFIER_error"; then
  ARGS="verifier_error_is_error"
elif match "$TASK" "memcleanup"; then
    ARGS="no_error_recovery,memleak_is_error,exit_leaks"
elif match "$TASK" "memtrack"; then
  ARGS="no_error_recovery,memleak_is_error"
elif match "$TASK" "deref" || match "$TASK" "free"; then
  ARGS="no_error_recovery"
elif match "$TASK" "overflow"; then
  ARGS="no_error_recovery"
fi

if test ! x = "x$DEPTH"; then
    ARGS="$ARGS,depth_limit:$DEPTH"
fi

if test ! x = "x$XMLTRACE"; then
    ARGS="$ARGS,xml_trace:$XMLTRACE"
fi

if [ -z $ENABLE_LLVM ]; then
    "$GCC_HOST"                                         \
        -fplugin="${SL_PLUG}"                           \
        -fplugin-arg-libsl-args="$ARGS"                 \
        -fplugin-arg-libsl-preserve-ec                  \
        -o /dev/null -O0 -S -xc $SRC_FILE $CFLAGS 2>&1               \
        | tee "$TRACE"                                  \
        | parse_output
else
    "$CLANG_HOST" -S -emit-llvm -O0 -g -o -             \
        -Xclang -fsanitize-address-use-after-scope $SRC_FILE $CFLAGS \
        | "$OPT_HOST" -lowerswitch                      \
        -unreachableblockelim                           \
        -load "$PASSES_LIB" -global-vars -nestedgep     \
        -load "$SL_PLUG" -sl -args="$ARGS"              \
        -preserve-ec                                    \
        -o /dev/null 2>&1                               \
        | tee "$TRACE"                                  \
        | parse_output
fi
