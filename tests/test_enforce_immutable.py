from pure_function_decorators import enforce_immutable


@enforce_immutable
def touch_list(a):
    a.append(3)
    return sum(a)


def test_mutation_prevented():
    test_list = [1, 2, 3]
    touch_list(test_list)
    assert test_list == [1, 2, 3]


@enforce_immutable
def pure(a):
    return tuple(sorted(a))


def test_no_mutation():
    assert pure({3, 1, 2}) == (1, 2, 3)
