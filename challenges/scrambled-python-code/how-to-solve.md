# Scrambled Python Code: how to solve

## Identify and inspect the artifact

Run the requested identification command against the original download:

```sh
file collision.pyc
```

Record its classification privately, and note the bytecode version for the next step. A compiled module is not necessarily encrypted. Its constants and instructions may directly reveal how it checks an input.

Use a disassembler that understands the version reported in the header. For example, `xdis` can inspect older bytecode from a newer Python interpreter:

```sh
python -m venv .venv
.venv/bin/python -m pip install xdis
.venv/bin/pydisasm collision.pyc
```

On Windows, use the corresponding executables under `.venv\Scripts\`. Reading this artifact as bytecode avoids executing its module body during inspection. A decompiler can help, but a complete reconstruction of the original source is unnecessary.

## Reconstruct the input check

In the disassembly, follow the construction of two integer lists. `BUILD_LIST` and `STORE_NAME` identify their boundaries and names. Preserve the order and repeated values; collecting every numeric constant into one list would lose that structure.

The module converts the first command-line argument into characters, loops over list positions, and compares an XOR expression with the second list. Its logic is equivalent to:

```python
for i in range(len(arr)):
    if arr[i] ^ ord(candidate[i]) != compArr[i]:
        reject()
accept()
```

XOR is its own inverse, so isolate the unknown character code at each position:

```text
character_code[i] = arr[i] XOR compArr[i]
```

Transcribe the two arrays locally from the disassembly, then apply:

```python
def recover_candidate(arr, comp_arr):
    if len(arr) != len(comp_arr):
        raise ValueError("Mismatched comparison lists")
    return "".join(chr(a ^ b) for a, b in zip(arr, comp_arr))

def matches_reconstructed_check(candidate, arr, comp_arr):
    return len(candidate) == len(arr) and all(
        a ^ ord(char) == b
        for char, a, b in zip(candidate, arr, comp_arr)
    )
```

## Check your work

Verify every recovered character against the reconstructed comparison, not just a recognizable prefix. This verifies the relevant logic without depending on a decompiler or importing the downloaded module. The arrays and recovered candidate are omitted here so the repository contains no stored solution material.
