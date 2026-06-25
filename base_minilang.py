class MinilangError(Exception):
    pass


_KEYWORDS = {
    "let", "print", "return", "if", "else",
    "while", "for", "fn", "true", "false", "null",
}

_TWO_CHARS = {"==", "!=", "<=", ">=", "&&", "||"}
_ONE_CHARS = set("+-*/%<>=!(){};,[]")


def _tokenize(source):
    tokens = []
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        if ch in " \t\r\n":
            i += 1
            continue

        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue

        if ch == '"':
            i += 1
            chars = []
            while True:
                if i >= n:
                    raise MinilangError("unterminated string")
                ch = source[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\":
                    if i + 1 >= n:
                        raise MinilangError("unterminated string escape")
                    esc = source[i + 1]
                    if esc == "n":
                        chars.append("\n")
                    elif esc == "t":
                        chars.append("\t")
                    elif esc == "r":
                        chars.append("\r")
                    elif esc == '"':
                        chars.append('"')
                    elif esc == "\\":
                        chars.append("\\")
                    else:
                        chars.append(esc)
                    i += 2
                    continue
                chars.append(ch)
                i += 1
            tokens.append(("STRING", "".join(chars)))
            continue

        if ch.isdigit():
            j = i
            while j < n and source[j].isdigit():
                j += 1
            if j < n and source[j] == ".":
                if j + 1 >= n or not source[j + 1].isdigit():
                    raise MinilangError("malformed number")
                j += 1
                while j < n and source[j].isdigit():
                    j += 1
                tokens.append(("NUMBER", float(source[i:j])))
            else:
                tokens.append(("NUMBER", int(source[i:j])))
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            word = source[i:j]
            if word in _KEYWORDS:
                tokens.append(("KW", word))
            else:
                tokens.append(("IDENT", word))
            i = j
            continue

        two = source[i:i + 2]
        if two in _TWO_CHARS:
            tokens.append(("SYM", two))
            i += 2
            continue

        if ch in _ONE_CHARS:
            tokens.append(("SYM", ch))
            i += 1
            continue

        raise MinilangError("unexpected character: " + repr(ch))

    tokens.append(("EOF", None))
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def _peek(self, offset=0):
        index = self.pos + offset
        if index >= len(self.tokens):
            return ("EOF", None)
        return self.tokens[index]

    def _check(self, kind=None, value=None):
        tok = self._peek()
        if kind is not None and tok[0] != kind:
            return False
        if value is not None and tok[1] != value:
            return False
        return True

    def _take(self, kind=None, value=None):
        if not self._check(kind, value):
            raise MinilangError("parse error: expected %r %r got %r"
                                % (kind, value, self._peek()))
        tok = self._peek()
        self.pos += 1
        return tok

    def _accept(self, value):
        if self._check("SYM", value):
            self.pos += 1
            return True
        return False

    def parse(self):
        statements = []
        while not self._check("EOF"):
            statements.append(self._statement(True))
        return statements

    def _statement(self, top_level):
        if self._check("KW", "let"):
            return self._let_statement()
        if self._check("KW", "print"):
            return self._print_statement()
        if self._check("KW", "return"):
            return self._return_statement()
        if self._check("KW", "if"):
            return self._if_statement()
        if self._check("KW", "while"):
            return self._while_statement()
        if self._check("KW", "for"):
            return self._for_statement()
        if self._check("KW", "fn"):
            if not top_level:
                raise MinilangError("function declarations must be top-level")
            return self._function_statement()

        expr = self._expression()
        if self._accept("="):
            value = self._expression()
            self._take("SYM", ";")
            return self._make_assignment(expr, value)

        self._take("SYM", ";")
        return ("expr", expr)

    def _make_assignment(self, target, value):
        if target[0] == "var":
            return ("assign", target[1], value)
        if target[0] == "index":
            return ("index_assign", target[1], target[2], value)
        raise MinilangError("invalid assignment target")

    def _assignment_no_semicolon(self):
        target = self._expression()
        self._take("SYM", "=")
        value = self._expression()
        return self._make_assignment(target, value)

    def _let_statement(self):
        self._take("KW", "let")
        name = self._take("IDENT")[1]
        self._take("SYM", "=")
        expr = self._expression()
        self._take("SYM", ";")
        return ("let", name, expr)

    def _print_statement(self):
        self._take("KW", "print")
        expr = self._expression()
        self._take("SYM", ";")
        return ("print", expr)

    def _return_statement(self):
        self._take("KW", "return")
        if self._check("SYM", ";"):
            self._take("SYM", ";")
            return ("return", ("literal", None))
        expr = self._expression()
        self._take("SYM", ";")
        return ("return", expr)

    def _if_statement(self):
        self._take("KW", "if")
        self._take("SYM", "(")
        cond = self._expression()
        self._take("SYM", ")")
        then_block = self._block()
        else_block = None
        if self._check("KW", "else"):
            self._take("KW", "else")
            else_block = self._block()
        return ("if", cond, then_block, else_block)

    def _while_statement(self):
        self._take("KW", "while")
        self._take("SYM", "(")
        cond = self._expression()
        self._take("SYM", ")")
        body = self._block()
        return ("while", cond, body)

    def _for_statement(self):
        self._take("KW", "for")
        self._take("SYM", "(")

        if self._check("KW", "let"):
            init = self._let_statement()
        else:
            init = self._assignment_no_semicolon()
            self._take("SYM", ";")

        cond = self._expression()
        self._take("SYM", ";")

        step = self._assignment_no_semicolon()

        self._take("SYM", ")")
        body = self._block()
        return ("for", init, cond, step, body)

    def _function_statement(self):
        self._take("KW", "fn")
        name = self._take("IDENT")[1]
        self._take("SYM", "(")
        params = []
        seen = set()
        if not self._check("SYM", ")"):
            while True:
                param = self._take("IDENT")[1]
                if param in seen:
                    raise MinilangError("duplicate parameter: " + param)
                seen.add(param)
                params.append(param)
                if not self._accept(","):
                    break
        self._take("SYM", ")")
        body = self._block()
        return ("fn", name, params, body)

    def _block(self):
        self._take("SYM", "{")
        statements = []
        while not self._check("SYM", "}"):
            if self._check("EOF"):
                raise MinilangError("unterminated block")
            statements.append(self._statement(False))
        self._take("SYM", "}")
        return statements

    def _expression(self):
        return self._or_expr()

    def _or_expr(self):
        left = self._and_expr()
        while self._check("SYM", "||"):
            op = self._take("SYM")[1]
            right = self._and_expr()
            left = ("logical", op, left, right)
        return left

    def _and_expr(self):
        left = self._comparison_expr()
        while self._check("SYM", "&&"):
            op = self._take("SYM")[1]
            right = self._comparison_expr()
            left = ("logical", op, left, right)
        return left

    def _comparison_expr(self):
        left = self._term_expr()
        while self._check("SYM") and self._peek()[1] in ("==", "!=", "<", "<=", ">", ">="):
            op = self._take("SYM")[1]
            right = self._term_expr()
            left = ("binary", op, left, right)
        return left

    def _term_expr(self):
        left = self._factor_expr()
        while self._check("SYM") and self._peek()[1] in ("+", "-"):
            op = self._take("SYM")[1]
            right = self._factor_expr()
            left = ("binary", op, left, right)
        return left

    def _factor_expr(self):
        left = self._unary_expr()
        while self._check("SYM") and self._peek()[1] in ("*", "/", "%"):
            op = self._take("SYM")[1]
            right = self._unary_expr()
            left = ("binary", op, left, right)
        return left

    def _unary_expr(self):
        if self._check("SYM") and self._peek()[1] in ("!", "-"):
            op = self._take("SYM")[1]
            expr = self._unary_expr()
            return ("unary", op, expr)
        return self._postfix_expr()

    def _postfix_expr(self):
        expr = self._primary_expr()
        while self._check("SYM", "["):
            self._take("SYM", "[")
            index = self._expression()
            self._take("SYM", "]")
            expr = ("index", expr, index)
        return expr

    def _primary_expr(self):
        if self._check("NUMBER"):
            return ("literal", self._take("NUMBER")[1])

        if self._check("STRING"):
            return ("literal", self._take("STRING")[1])

        if self._check("KW", "true"):
            self._take("KW", "true")
            return ("literal", True)

        if self._check("KW", "false"):
            self._take("KW", "false")
            return ("literal", False)

        if self._check("KW", "null"):
            self._take("KW", "null")
            return ("literal", None)

        if self._accept("("):
            expr = self._expression()
            self._take("SYM", ")")
            return expr

        if self._accept("["):
            elements = []
            if not self._check("SYM", "]"):
                while True:
                    elements.append(self._expression())
                    if not self._accept(","):
                        break
            self._take("SYM", "]")
            return ("array", elements)

        if self._check("IDENT"):
            name = self._take("IDENT")[1]
            if self._accept("("):
                args = []
                if not self._check("SYM", ")"):
                    while True:
                        args.append(self._expression())
                        if not self._accept(","):
                            break
                self._take("SYM", ")")
                return ("call", name, args)
            return ("var", name)

        raise MinilangError("parse error: unexpected token " + repr(self._peek()))


class _ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class _Function:
    def __init__(self, name, params, body):
        self.name = name
        self.params = params
        self.body = body


def _is_number(value):
    return (type(value) is int) or (type(value) is float)


class _Interpreter:
    def __init__(self):
        self.functions = {}
        self.output = []

    def run_program(self, statements):
        for stmt in statements:
            if stmt[0] == "fn":
                name = stmt[1]
                if name in self.functions:
                    raise MinilangError("duplicate function: " + name)
                self.functions[name] = _Function(name, stmt[2], stmt[3])

        env = {}
        try:
            for stmt in statements:
                if stmt[0] != "fn":
                    self._run_statement(stmt, env)
        except _ReturnSignal:
            raise MinilangError("return outside function")

        return "".join(self.output)

    def _run_block(self, statements, env):
        for stmt in statements:
            self._run_statement(stmt, env)

    def _run_statement(self, stmt, env):
        kind = stmt[0]

        if kind == "let":
            env[stmt[1]] = self._value(stmt[2], env)
            return

        if kind == "assign":
            name = stmt[1]
            if name not in env:
                raise MinilangError("assignment to undeclared variable: " + name)
            env[name] = self._value(stmt[2], env)
            return

        if kind == "index_assign":
            container = self._value(stmt[1], env)
            index = self._value(stmt[2], env)
            if type(container) is not list:
                raise MinilangError("index assignment requires an array")
            if type(index) is not int:
                raise MinilangError("array index must be an integer")
            if index < 0 or index >= len(container):
                raise MinilangError("array index out of range")
            container[index] = self._value(stmt[3], env)
            return

        if kind == "print":
            self.output.append(self._text(self._value(stmt[1], env)) + "\n")
            return

        if kind == "return":
            raise _ReturnSignal(self._value(stmt[1], env))

        if kind == "if":
            if self._truth(self._value(stmt[1], env)):
                self._run_block(stmt[2], env)
            elif stmt[3] is not None:
                self._run_block(stmt[3], env)
            return

        if kind == "while":
            while self._truth(self._value(stmt[1], env)):
                self._run_block(stmt[2], env)
            return

        if kind == "for":
            init = stmt[1]
            cond = stmt[2]
            step = stmt[3]
            body = stmt[4]
            self._run_statement(init, env)
            while self._truth(self._value(cond, env)):
                self._run_block(body, env)
                self._run_statement(step, env)
            return

        if kind == "expr":
            self._value(stmt[1], env)
            return

        if kind == "fn":
            raise MinilangError("function declaration in invalid position")

        raise MinilangError("unknown statement: " + str(kind))

    def _value(self, expr, env):
        kind = expr[0]

        if kind == "literal":
            return expr[1]

        if kind == "var":
            name = expr[1]
            if name not in env:
                raise MinilangError("undefined variable: " + name)
            return env[name]

        if kind == "array":
            return [self._value(element, env) for element in expr[1]]

        if kind == "index":
            container = self._value(expr[1], env)
            index = self._value(expr[2], env)
            if type(index) is not int:
                raise MinilangError("array index must be an integer")
            if type(container) is list:
                if index < 0 or index >= len(container):
                    raise MinilangError("array index out of range")
                return container[index]
            if type(container) is str:
                if index < 0 or index >= len(container):
                    raise MinilangError("string index out of range")
                return container[index]
            raise MinilangError("indexing requires an array or string")

        if kind == "unary":
            op = expr[1]
            value = self._value(expr[2], env)
            if op == "-":
                if not _is_number(value):
                    raise MinilangError("unary '-' requires a number")
                return -value
            if op == "!":
                return not self._truth(value)
            raise MinilangError("unknown unary operator: " + op)

        if kind == "logical":
            op = expr[1]
            left = self._value(expr[2], env)
            if op == "&&":
                if not self._truth(left):
                    return False
                return bool(self._truth(self._value(expr[3], env)))
            if op == "||":
                if self._truth(left):
                    return True
                return bool(self._truth(self._value(expr[3], env)))
            raise MinilangError("unknown logical operator: " + op)

        if kind == "binary":
            left = self._value(expr[2], env)
            right = self._value(expr[3], env)
            return self._binary(expr[1], left, right)

        if kind == "call":
            return self._call(expr[1], expr[2], env)

        raise MinilangError("unknown expression: " + str(kind))

    def _call(self, name, arg_exprs, env):
        if name in self.functions:
            fn = self.functions[name]
            if len(arg_exprs) != len(fn.params):
                raise MinilangError("wrong arity calling %s: expected %d got %d"
                                    % (name, len(fn.params), len(arg_exprs)))

            args = [self._value(arg, env) for arg in arg_exprs]
            local_env = {}
            for param, arg in zip(fn.params, args):
                local_env[param] = arg

            try:
                self._run_block(fn.body, local_env)
            except _ReturnSignal as ret:
                return ret.value

            return None

        if name == "len":
            if len(arg_exprs) != 1:
                raise MinilangError("wrong arity calling len: expected 1 got %d"
                                    % len(arg_exprs))
            value = self._value(arg_exprs[0], env)
            if type(value) is list or type(value) is str:
                return len(value)
            raise MinilangError("len requires an array or string")

        if name == "str":
            if len(arg_exprs) != 1:
                raise MinilangError("wrong arity calling str: expected 1 got %d"
                                    % len(arg_exprs))
            value = self._value(arg_exprs[0], env)
            return self._text(value)

        if name == "abs":
            if len(arg_exprs) != 1:
                raise MinilangError("wrong arity calling abs: expected 1 got %d"
                                    % len(arg_exprs))
            value = self._value(arg_exprs[0], env)
            if not _is_number(value):
                raise MinilangError("abs requires a number")
            return abs(value)

        if name == "max":
            if len(arg_exprs) != 2:
                raise MinilangError("wrong arity calling max: expected 2 got %d"
                                    % len(arg_exprs))
            a = self._value(arg_exprs[0], env)
            b = self._value(arg_exprs[1], env)
            self._require_comparable(a, b, "max")
            return a if a >= b else b

        if name == "min":
            if len(arg_exprs) != 2:
                raise MinilangError("wrong arity calling min: expected 2 got %d"
                                    % len(arg_exprs))
            a = self._value(arg_exprs[0], env)
            b = self._value(arg_exprs[1], env)
            self._require_comparable(a, b, "min")
            return a if a <= b else b

        raise MinilangError("calling a non-function: " + name)

    def _require_comparable(self, left, right, name):
        if _is_number(left) and _is_number(right):
            return
        if type(left) is str and type(right) is str:
            return
        raise MinilangError(name + " requires two numbers or two strings")

    def _binary(self, op, left, right):
        if op == "+":
            if type(left) is str and type(right) is str:
                return left + right
            if _is_number(left) and _is_number(right):
                return left + right
            raise MinilangError("'+' requires two numbers or two strings")

        if op == "-":
            self._require_numbers(left, right)
            return left - right

        if op == "*":
            self._require_numbers(left, right)
            return left * right

        if op == "/":
            self._require_numbers(left, right)
            if right == 0:
                raise MinilangError("division by zero")
            result = left / right
            if type(left) is int and type(right) is int and result == int(result):
                return int(result)
            return result

        if op == "%":
            self._require_numbers(left, right)
            if right == 0:
                raise MinilangError("modulo by zero")
            return left % right

        if op == "==":
            return self._same(left, right)

        if op == "!=":
            return not self._same(left, right)

        if op in ("<", "<=", ">", ">="):
            if _is_number(left) and _is_number(right):
                pass
            elif type(left) is str and type(right) is str:
                pass
            else:
                raise MinilangError("comparison requires two numbers or two strings")

            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            return left >= right

        raise MinilangError("unknown binary operator: " + op)

    def _require_numbers(self, left, right):
        if not (_is_number(left) and _is_number(right)):
            raise MinilangError("operation requires numbers")

    def _same(self, left, right):
        return self._same_inner(left, right, set())

    def _same_inner(self, left, right, seen):
        if _is_number(left) and _is_number(right):
            return left == right
        if type(left) is bool and type(right) is bool:
            return left == right
        if type(left) is str and type(right) is str:
            return left == right
        if type(left) is list and type(right) is list:
            pair = (id(left), id(right))
            if pair in seen:
                return True
            if len(left) != len(right):
                return False
            seen.add(pair)
            try:
                for a, b in zip(left, right):
                    if not self._same_inner(a, b, seen):
                        return False
                return True
            finally:
                seen.remove(pair)
        if left is None and right is None:
            return True
        return False

    def _truth(self, value):
        if value is None:
            return False
        if type(value) is bool:
            return value
        if _is_number(value):
            return value != 0
        if type(value) is str:
            return value != ""
        if type(value) is list:
            return len(value) != 0
        return True

    def _text(self, value):
        return self._text_inner(value, set())

    def _text_inner(self, value, seen):
        if value is None:
            return "null"
        if type(value) is bool:
            return "true" if value else "false"
        if type(value) is int:
            return str(value)
        if type(value) is float:
            return str(value)
        if type(value) is str:
            return value
        if type(value) is list:
            value_id = id(value)
            if value_id in seen:
                raise MinilangError("cannot stringify cyclic array")
            seen.add(value_id)
            try:
                parts = [self._element_text(element, seen) for element in value]
            finally:
                seen.remove(value_id)
            return "[" + ", ".join(parts) + "]"
        raise MinilangError("cannot stringify value")

    def _element_text(self, value, seen):
        if type(value) is str:
            return '"' + value + '"'
        return self._text_inner(value, seen)


def run(source: str) -> str:
    tokens = _tokenize(source)
    statements = _Parser(tokens).parse()
    return _Interpreter().run_program(statements)