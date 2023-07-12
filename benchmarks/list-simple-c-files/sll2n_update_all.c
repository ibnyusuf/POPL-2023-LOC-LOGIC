
extern void abort(void);
#include <assert.h>
void reach_error() { assert(0); }
extern int __VERIFIER_nondet_int();

/*
 * Create NULL-terminated sll of size 2: 1-1
 * Updates all nodes in a forward traversal. Check result: 2-3
 */
#include <stdlib.h>

typedef struct node {
  int data;
  struct node* next;
} *SLL;

void myexit(int s) {
 _EXIT: goto _EXIT;
}

int _get_nondet_int(int larger_than) {
  int res = __VERIFIER_nondet_int();
  while(res <= larger_than) {
    res = __VERIFIER_nondet_int();
  }
  return res;
}

SLL node_create(int data) {
  SLL temp = (SLL) malloc(sizeof(struct node));
  if(NULL == temp) {
    myexit(1);
  }
  temp->next = NULL;
  temp->data = data;
  return temp;
}

SLL sll_create(int len, int data) {
  SLL head = NULL;
  for(; len > 0; len--) {
    SLL new_head = node_create(data);
    new_head->next = head;
    head = new_head;
  }
  return head;
}

void sll_destroy(SLL head) {
  while(head) {
    SLL temp = head->next;
    free(head);
    head = temp;
  }
}

int sll_get_data_at(SLL head, int index) {
  while(index > 0) {
    head = head->next;
    index--;
  }
  return head->data;
}

void sll_update_at(SLL head, int data, int index) {
  while(index > 0) {
    head = head->next;
    index--;
  }
  head->data = data;
}

int main() {
  const int len = _get_nondet_int(0);
  const int data = 1;
  SLL s = sll_create(len, data);
  int i;
  for(i = 0; i < len; i++) {
    int new_data = i + len;
    sll_update_at(s, new_data, i);
  }
  for(i = 0; i < len; i++) {
    int expected = i + len;
    if(expected != sll_get_data_at(s, i)) {
      goto ERROR;
    }
  }
  sll_destroy(s);
  return 0;
 ERROR: {reach_error();abort();}
  return 1;
}