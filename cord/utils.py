def get(lst, **kwargs):
    """Get an object from a list that matches the search criteria in ``**kwargs``.

    Parameters
    ----------
    lst: list
        List to be searched.
    """

    for element in lst:
        for attr, val in kwargs.items():
            res = getattr(element, attr)
            if res == val:
                return element

    return None


def delete(lst, **kwargs):
    """Delete an element from a list that
    matches the search criteria in ``**kwargs``

    Parameters
    ----------
    lst: list
        List to be searched.
    """

    for (idx, element) in enumerate(lst):
        for attr, val in kwargs.items():
            res = getattr(element, attr)
            if res == val:
                del lst[idx]
