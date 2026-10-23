# Live Relay Cipher: how to solve

## Preserve bytes and parse the frames

Save the connection as raw bytes. Copying terminal output corrupts non-text bytes through character decoding and replacement symbols. On a system with Netcat and `timeout`, a bounded capture is:

```sh
timeout 45s nc services.cityinthe.cloud 4444 > relay.bin
```

An exit status caused by `timeout` is expected when ending a live stream. Verify the saved bytes rather than interpreting that exit status as a failed capture.

On Windows without Netcat, PowerShell can capture the same data:

```powershell
$client = [Net.Sockets.TcpClient]::new("services.cityinthe.cloud", 4444)
$capture = [IO.MemoryStream]::new()
try {
    $stream = $client.GetStream()
    $stream.ReadTimeout = 1500
    $buffer = New-Object byte[] 4096
    $until = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $until) {
        try {
            $count = $stream.Read($buffer, 0, $buffer.Length)
        } catch [IO.IOException] {
            if ($_.Exception.InnerException -is [Net.Sockets.SocketException] -and
                $_.Exception.InnerException.SocketErrorCode -eq [Net.Sockets.SocketError]::TimedOut) {
                continue
            }
            throw
        }
        if ($count -eq 0) { break }
        $capture.Write($buffer, 0, $count)
    }
    [IO.File]::WriteAllBytes((Join-Path $PWD "relay.bin"), $capture.ToArray())
} finally {
    $client.Close()
    $capture.Dispose()
}
```

Locate the banner's end marker, then parse fixed 40-byte frames. Network reads can split or combine frames; read boundaries do not define packet boundaries. Sequence numbers use big-endian byte order.

```python
from pathlib import Path
import struct

def read_frames(path):
    raw = Path(path).read_bytes()
    marker = b"--- BEGIN BINARY STREAM ---\n"
    marker_at = raw.find(marker)
    if marker_at < 0:
        raise ValueError("Stream banner missing")
    stream = raw[marker_at + len(marker):]
    frames = []
    for offset in range(0, len(stream) - 39, 40):
        magic, kind, sequence, length = struct.unpack(">2sBIB", stream[offset:offset + 8])
        if magic != b"L8" or kind not in (1, 2) or length > 32:
            raise ValueError("Invalid frame; check capture alignment")
        frames.append((kind, sequence, length, stream[offset + 8:offset + 40]))
    return frames, len(stream) % 40
```

Keep any partial final frame out of analysis. Repeated sequence numbers with identical bodies are retransmissions; do not count them as independent evidence. Do not combine captures under an assumed shared key: separate connections in this session produced different traffic.

## Interpret the tap polynomials

The masks include the leading polynomial term. Their highest exponents are 17, 19, and 23, so the state widths are 17, 19, and 23 bits. Treating each mask's bit length as the width adds an incorrect state bit and prevents recovery.

The register update that matched this capture shifts right, calculates parity from the selected taps, and inserts that bit at the high end:

```python
WIDTHS = (17, 19, 23)
TAPS = (0x20009, 0x80027, 0x800021)

def step(state, width, taps):
    feedback = (state & taps).bit_count() & 1
    return (state >> 1) | (feedback << (width - 1))
```

The leading term is outside the state and contributes no bit to the parity calculation. The first register controls which of the other two advances. The emitted bit is the XOR of the low bits of those two data registers. The following schedule matched the captured STATUS frames:

```python
def clock_and_emit(registers):
    choose = registers[0] & 1
    registers[0] = step(registers[0], WIDTHS[0], TAPS[0])
    selected = 1 if choose else 2
    registers[selected] = step(registers[selected], WIDTHS[selected], TAPS[selected])
    return (registers[1] ^ registers[2]) & 1
```

Pack emitted bits from most significant to least significant within each byte. Tap masks alone did not establish this clocking rule: readable STATUS messages and consistent padding provided the check.

## Use STATUS padding as known plaintext

The STATUS header gives a plaintext length while the encrypted body is always 32 bytes. The matching model uses padding consisting of `32 - length` repeated bytes, each equal to that value. Test that hypothesis rather than assuming the unused part is zero-filled.

At each padding position:

```text
known_keystream_byte = ciphertext_byte XOR padding_byte
```

Those suffixes provide enough known bits to recover generator state without guessing the STATUS sentence.

## Recover state using binary linear equations

Enumerate the `2^17` possible initial states of the control register. For each candidate, the clock schedule of both data registers becomes known. Their outputs are then linear functions of their 19 and 23 unknown initial bits.

Represent each symbolic state bit by a bitmask over those 42 unknowns. Apply the same shift and XOR feedback operations to the bitmasks. An emitted bit produces one linear equation. Compare it with the known keystream bit at padding positions and solve incrementally using Gaussian elimination over binary values.

```text
for each possible control state:
    set the two symbolic data states to independent basis vectors
    simulate the control schedule across the entire frame
    at each known padding bit:
        form the symbolic output equation
        add it to a binary elimination basis
        reject this control state if the equations contradict one another
    recover data-register values for any surviving, fully constrained basis
    decrypt the full STATUS body and verify every padding byte
```

With no emitted plaintext before the first update, use `clock_and_emit` directly. Alternatively, a solver can recover state immediately before an output and model output before the next update. That representation has one initial clock already applied. Keep this phase difference explicit when converting the recovered state back to initialization state.

A candidate must explain more than the bits used to fit it. Verify the remaining padding bits and readable STATUS content, then repeat with several distinct sequence numbers.

## Remove sequence initialization

Recover the common state after key loading instead of searching for the original key. The inverse register step is available because the low feedback tap is present:

```python
def inverse_step(state, width, taps):
    shifted = (state & ((1 << (width - 1)) - 1)) << 1
    low = (state >> (width - 1)) ^ ((shifted & taps).bit_count() & 1)
    return shifted | low
```

To reverse a generator clock, reverse the control register first. Its previous low bit identifies which data register to reverse. Undo any initial output-phase clock in the state representation used by the solver.

For this capture, the 32 sequence bits were mixed least significant bit first. For each bit, all registers XOR that bit into their low position and then perform a regular register step. Reverse those operations in reverse bit order. Independent STATUS frames should then yield the same state immediately after key loading.

This state is sufficient to initialize any sequence number from the same connection:

```python
def load_sequence(after_key_state, sequence):
    registers = list(after_key_state)
    for bit_index in range(32):
        bit = (sequence >> bit_index) & 1
        registers = [
            step(value ^ bit, width, taps)
            for value, width, taps in zip(registers, WIDTHS, TAPS)
        ]
    return registers
```

No recovered register values or key-equivalent state are stored in this guide.

## Decrypt and verify

Initialize from the common state and each frame's sequence number, generate 256 bits with `clock_and_emit`, pack them into 32 bytes, and XOR them with the body.

The recovered model was verified against all 169 STATUS frames in the supplied capture: every plaintext prefix was printable, and every padding suffix matched its declared length. The same initialization and stepping rule then decoded the SECURE frame.

The SECURE frame's length field was zero, and its trailing bytes did not follow the STATUS padding convention. Decrypt its entire body and inspect the payload locally; do not discard it as an empty message or blindly apply STATUS unpadding. Recovered output, submission values, raw captures, and solver logs are excluded from this repository.
