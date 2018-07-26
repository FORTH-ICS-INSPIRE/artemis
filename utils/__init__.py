def flatten(items, seqtypes=(list, tuple)):
    if not isinstance(items, seqtypes):
        return [items]
    for i in range(len(items)):
        while i < len(items) and isinstance(items[i], seqtypes):
            items[i:i+1] = items[i]
    return items
