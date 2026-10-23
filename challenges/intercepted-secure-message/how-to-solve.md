# Intercepted Secure Message: how to solve

## Phonetic words

The first transmission uses spelling words separated by hyphens. Each spelling word represents its initial letter. Preserve the spaces between complete words while replacing each hyphen-separated token with its initial.

```python
def decode_spelling_words(text):
    return " ".join(
        "".join(token[0] for token in word.split("-"))
        for word in text.strip().split()
    )
```

Check that every token belongs to the spelling alphabet before decoding. The result should be a grammatical sentence. Keep its words separated when submitting it privately.

## Dot groups

The second transmission contains dots without dashes. Count dots rather than interpreting the groups as Morse symbols. Each letter has two counts: a row and a column in a five-by-five grid. This convention shares a cell between C and K.

```text
    1 2 3 4 5
1   A B C D E
2   F G H I J
3   L M N O P
4   Q R S T U
5   V W X Y Z
```

The supplied text uses one space within a letter, two between letters, and three between words. Preserve those distinctions when copying it.

```python
import re

GRID = "ABCDEFGHIJLMNOPQRSTUVWXYZ"

def decode_dot_groups(text):
    words = []
    for word in re.split(r" {3,}", text.strip()):
        letters = []
        for pair in re.split(r" {2}", word):
            row, col = pair.split()
            if set(row + col) != {"."}:
                raise ValueError("Expected dots only")
            r, c = len(row), len(col)
            if not (1 <= r <= 5 and 1 <= c <= 5):
                raise ValueError("Dot count outside the grid")
            letters.append(GRID[5 * (r - 1) + c - 1])
        words.append("".join(letters))
    return " ".join(words)
```

If spacing was lost, tokenize individual dot groups, pair adjacent groups, and restore word boundaries from the original prompt. Verify every pair stays within the grid and the entire result reads naturally. No decoded sentence is recorded here.
