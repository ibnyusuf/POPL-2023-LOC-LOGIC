struct Node {
  Int data;
  Node* next;
};

func main() {
  Node* head = NULL;
  const Int len;
  const Int dat = 1;

  Int i = len;
  while(i > 0) {
    Node* node = malloc();
    node->next = NULL;
    node->data = dat;
    node->next = head;
    head = node;
    i = i - 1;
  }

  Node* node2 = malloc();
  node2->next = head;
  node2->data = dat;
  head = node2;

  Int count = 0;
  while(head != NULL) {
    head = head->next;
    count = count + 1;
  }

}

(axiom
  (<= 0 (value_const len))
)

(conjecture
  (= (value main_end count) (+ (value_const len) 1))
)