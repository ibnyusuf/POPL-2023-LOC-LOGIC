#include <getopt.h>

extern int __symbiotic_nondet_int(void);
extern void klee_warning(const char *);

int getopt_long(int argc, char * const argv[],
           const char *optstring,
           const struct option *longopts, int *longindex) {

	klee_warning("unsupported function model");
	return __symbiotic_nondet_int();
}

