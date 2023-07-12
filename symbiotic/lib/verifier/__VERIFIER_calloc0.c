#include "symbiotic-size_t.h"

extern void *malloc(size_t);
extern void *memset(void *s, int c, size_t n);
extern void __VERIFIER_assume(int);

void *__VERIFIER_calloc0(size_t nmem, size_t size)
{
	void *mem = malloc(nmem * size);
	__VERIFIER_assume(mem != (void *)0);
	memset(mem, 0, nmem * size);

	return mem;
}

