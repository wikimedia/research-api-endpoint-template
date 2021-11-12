import time

from anytree import Node, RenderTree, PostOrderIter, PreOrderIter, NodeMixin
from anytree.util import leftsibling

class OrderedNode(NodeMixin):  # Add Node feature
    def __init__(self, name, ntype='Text', text_hash=None, idx=-1, text='', char_offset=0, parent=None, children=None):
        super(OrderedNode, self).__init__()
        self.name = name
        self.ntype = ntype
        self.text = str(text)
        if text_hash is None:
            self.text_hash = hash(self.text)
        else:
            self.text_hash = hash(str(text_hash))
        self.idx = idx
        self.char_offset = char_offset
        self.parent = parent
        if children:
            self.children = children

    def leftmost(self):
        return self.idx if self.is_leaf else self.children[0].leftmost()


def simple_node_class(node):
    """e.g., "<class 'mwparserfromhell.nodes.heading.Heading'>" -> "Heading"."""
    return str(type(node)).split('.')[-1].split("'")[0]


def sec_to_name(s):
    """Converts a section to an interpretible name."""
    return str(s.nodes[0].title) + f' (S.{s.nodes[0].level})'


def node_to_name(n):
    """Converts a mwparserfromhell node to an interpretible name."""
    n_txt = n.replace("\n", "\\n")
    if len(n_txt) > 13:
        return f'{simple_node_class(n)}: {n_txt[:10]}...'
    else:
        return f'{simple_node_class(n)}: {n_txt}'

def sec_node_tree(wt):
    root = OrderedNode('root', ntype="Article")
    parent_by_level = {1: root}
    secname_to_text = {}
    for s in wt.get_sections():
        if s:
            sec_hash = sec_to_name(s)
            sec_lvl = s.nodes[0].level
            sec_text = str(s.nodes[0])
            for n in s.nodes[1:]:
                if simple_node_class(n) == 'Heading':
                    break
                sec_text += str(n)
            secname_to_text[sec_hash] = sec_text
            s_node = OrderedNode(sec_hash, ntype="Heading", text=s.nodes[0], text_hash=sec_text, char_offset=0, parent=parent_by_level[sec_lvl-1])
            parent_by_level[sec_lvl] = s_node
            char_offset = len(s_node.text)
            for n in s.nodes[1:]:
                if simple_node_class(n) == 'Heading':
                    break
                n_node = OrderedNode(node_to_name(n), ntype=simple_node_class(n), text=n, char_offset=char_offset, parent=s_node)
                char_offset += len(str(n))
    return root, secname_to_text

def format_diff(node):
    result = {'name':node.name,
              'type':node.ntype,
              'offset':node.char_offset,
              'size':len(node.text)}
    if node.ntype == 'Heading':
        result['section'] = node.name
    else:
        result['section'] = node.parent.name
    return result

def format_result(diff, sections1, sections2):
    result = {'remove':[], 'insert':[], 'change':[], 'sections-prev':{}, 'sections-curr':{}}
    for n in diff['remove']:
        n_res = format_diff(n)
        result['remove'].append(n_res)
        result['sections-prev'][n_res['section']] = sections1[n_res['section']]
    for n in diff['insert']:
        n_res = format_diff(n)
        result['insert'].append(n_res)
        result['sections-curr'][n_res['section']] = sections2[n_res['section']]
    for pn, cn in diff['change']:
        pn_res = format_diff(pn)
        cn_res = format_diff(cn)
        result['change'].append({'prev':pn_res, 'curr':cn_res})
        result['sections-prev'][pn_res['section']] = sections1[pn_res['section']]
        result['sections-curr'][cn_res['section']] = sections2[cn_res['section']]
    return result


class Differ:

    def __init__(self, t1, t2, timeout=2):
        self.t1 = [n for n in PostOrderIter(t1)]
        self.t2 = [n for n in PostOrderIter(t2)]
        self.prune_trees()
        for i, n in enumerate(self.t1):
            n.idx = i
        for i, n in enumerate(self.t2):
            n.idx = i
        self.timeout = time.time() + timeout
        self.ins_cost = 1
        self.rem_cost = 1
        self.chg_cost = 1
        self.nodetype_chg_cost = 100  # arbitrarily high to require changes to only occur w/i same nodes

        # Permanent store of transactions such that transactions[x][y] is the minimum
        # transactions to get from the sub-tree rooted at node x (in tree1) to the sub-tree
        # rooted at node y (in tree2).
        self.transactions = {None: {}}
        # Indices for each transaction, to avoid high performance cost of creating the
        # transactions multiple times
        self.transaction_to_idx = {None: {None: 0}}
        # All possible transactions
        self.idx_to_transaction = [(None, None)]

        idx_transaction = 1  # starts with nulls inserted

        transactions = {None: {None: []}}

        # Populate transaction stores
        for i in range(0, len(self.t1)):
            transactions[i] = {None: []}
            self.transaction_to_idx[i] = {None: idx_transaction}
            idx_transaction += 1
            self.idx_to_transaction.append((i, None))
            for j in range(0, len(self.t2)):
                transactions[None][j] = []
                transactions[i][j] = []
                self.transaction_to_idx[None][j] = idx_transaction
                idx_transaction += 1
                self.idx_to_transaction.append((None, j))
                self.transaction_to_idx[i][j] = idx_transaction
                idx_transaction += 1
                self.idx_to_transaction.append((i, j))
            self.transactions[i] = {}
        self.populate_transactions(transactions)

    def prune_trees(self):
        """Quick heuristic preprocessing to reduce tree differ time.

        Prune nodes from any sections that align across revisions to reduce tree size while maintaining structure.
        """
        t1_sections = [n for n in self.t1 if n.ntype == "Heading"]
        t2_sections = [n for n in self.t2 if n.ntype == "Heading"]
        prune = []
        for secnode1 in t1_sections:
            for sn2_idx in range(len(t2_sections)):
                secnode2 = t2_sections[sn2_idx]
                if secnode1.text_hash == secnode2.text_hash:
                    prune.append(secnode1)
                    prune.append(secnode2)
                    t2_sections.pop(sn2_idx)  # only match once
                    break
        for n in prune:
            # only keep section children and remove all other nodes
            n.children = [c for c in n.children if c.ntype == "Heading"]

        # remove nodes from t1/t2 structures
        for i in range(len(self.t1) - 1, -1, -1):
            if not self.t1[i].name == 'root' and self.t1[i].parent is None:
                self.t1.pop(i)
        for i in range(len(self.t2) - 1, -1, -1):
            if not self.t2[i].name == 'root' and self.t2[i].parent is None:
                self.t2.pop(i)

    def get_key_roots(self, tree):
        """Get keyroots (node has a left sibling or is the root) of a tree"""
        for on in tree:
            if on.is_root or leftsibling(on) is not None:
                yield on

    def populate_transactions(self, transactions):
        """Populate self.transactions with minimum transactions between all possible trees"""
        for kr1 in self.get_key_roots(self.t1):
            # Make transactions for tree -> null
            i_nulls = []
            for ii in range(kr1.leftmost(), kr1.idx + 1):
                i_nulls.append(self.transaction_to_idx[ii][None])
                transactions[ii][None] = i_nulls.copy()
            for kr2 in self.get_key_roots(self.t2):
                # Make transactions of null -> tree
                j_nulls = []
                for jj in range(kr2.leftmost(), kr2.idx + 1):
                    j_nulls.append(self.transaction_to_idx[None][jj])
                    transactions[None][jj] = j_nulls.copy()

                # get the diff
                self.find_minimum_transactions(kr1, kr2, transactions)
                if time.time() > self.timeout:
                    self.transactions = None
                    return

        for i in range(0, len(self.t1)):
            for j in range(0, len(self.t2)):
                if self.transactions.get(i, {}).get(j) and len(self.transactions[i][j]) > 0:
                    self.transactions[i][j] = tuple([self.idx_to_transaction[idx] for idx in self.transactions[i][j]])

    def get_node_distance(self, n1, n2):
        """
        Get the cost of:
        * removing a node from the first tree,
        * inserting a node into the second tree,
        * or relabelling a node from the first tree to a node from the second tree.
        """
        if n1 is None and n2 is None:
            return 0
        elif n1 is None:
            return self.ins_cost
        elif n2 is None:
            return self.rem_cost
        # Inserts/Removes are easy. Changes are more complicated and should only be within same node type.
        # Use arbitrarily high-value for nodetype changes to effectively ban.
        elif n1.ntype != n2.ntype:
            return self.nodetype_chg_cost
        # next two functions check if both nodes are the same (criteria varies by nodetype)
        elif n1.ntype in ['Heading', "Paragraph"]:
            if n1.text == n2.text:
                return 0
            else:
                return self.chg_cost
        elif n1.text_hash == n2.text_hash:
            return 0
        # otherwise, same node types and not the same, then change cost
        else:
            return self.chg_cost

    def get_lowest_cost(self, rc, ic, cc):
        min_cost = rc
        index = 0
        if ic < min_cost:
            index = 1
            min_cost = ic
        if cc < min_cost:
            index = 2
        return index

    def find_minimum_transactions(self, kr1, kr2, transactions):
        """Find the minimum transactions to get from the first tree to the second tree."""
        for i in range(kr1.leftmost(), kr1.idx + 1):
            if i == kr1.leftmost():
                i_minus_1 = None
            else:
                i_minus_1 = i - 1
            n1 = self.t1[i]
            for j in range(kr2.leftmost(), kr2.idx + 1):
                if j == kr2.leftmost():
                    j_minus_1 = None
                else:
                    j_minus_1 = j - 1
                n2 = self.t2[j]

                if n1.leftmost() == kr1.leftmost() and n2.leftmost() == kr2.leftmost():
                    rem = transactions[i_minus_1][j]
                    ins = transactions[i][j_minus_1]
                    chg = transactions[i_minus_1][j_minus_1]
                    node_distance = self.get_node_distance(n1, n2)
                    # cost of each transaction
                    transaction = self.get_lowest_cost(len(rem) + self.rem_cost,
                                                       len(ins) + self.ins_cost,
                                                       len(chg) + node_distance)
                    if transaction == 0:
                        # record a remove
                        rc = rem.copy()
                        rc.append(self.transaction_to_idx[i][None])
                        transactions[i][j] = rc
                    elif transaction == 1:
                        # record an insert
                        ic = ins.copy()
                        ic.append(self.transaction_to_idx[None][j])
                        transactions[i][j] = ic
                    else:
                        # If nodes i and j are different, record a change, otherwise there is no transaction
                        transactions[i][j] = chg.copy()
                        if node_distance == 1:
                            transactions[i][j].append(self.transaction_to_idx[i][j])

                    self.transactions[i][j] = transactions[i][j].copy()
                else:
                    # Previous transactions, leading up to a remove, insert or change
                    rem = transactions[i_minus_1][j]
                    ins = transactions[i][j_minus_1]

                    if n1.leftmost() - 1 < kr1.leftmost():
                        k1 = None
                    else:
                        k1 = n1.leftmost() - 1
                    if n2.leftmost() - 1 < kr2.leftmost():
                        k2 = None
                    else:
                        k2 = n2.leftmost() - 1
                    chg = transactions[k1][k2]

                    transaction = self.get_lowest_cost(len(rem) + self.rem_cost,
                                                       len(ins) + self.ins_cost,
                                                       len(chg) + len(self.transactions[i][j]))
                    if transaction == 0:
                        # record a remove
                        rc = rem.copy()
                        rc.append(self.transaction_to_idx[i][None])
                        transactions[i][j] = rc
                    elif transaction == 1:
                        # record an insert
                        ic = ins.copy()
                        ic.append(self.transaction_to_idx[None][j])
                        transactions[i][j] = ic
                    else:
                        # record a change
                        cc = chg.copy()
                        cc.extend(self.transactions[i][j])
                        transactions[i][j] = cc

    def get_corresponding_nodes(self):
        """Explain transactions"""
        # Get inserts/removals/changes based on final set of transactions
        transactions = self.transactions[len(self.t1) - 1][len(self.t2) - 1]
        remove = []
        insert = []
        change = []
        for i in range(0, len(transactions)):
            if transactions[i][0] is None:
                ins_node = self.t2[transactions[i][1]]
                insert.append(ins_node)
            elif transactions[i][1] is None:
                rem_node = self.t1[transactions[i][0]]
                remove.append(rem_node)
            else:
                prev_node = self.t1[transactions[i][0]]
                curr_node = self.t2[transactions[i][1]]
                change.append((prev_node, curr_node))
        return {'remove': remove, 'insert': insert, 'change': change}