# Blurred Messages

We intercepted data from Liber8tion. Last year they slipped up and exposed messages, but they have since started redacting sensitive information. Can you recover the latest key from their blurred message?

The supplied artifacts are `message1.png`, a readable example message, and `message2.png`, a blurred line. Obtain the original images separately. They are not included here because they contain the example and recoverable challenge responses.

The flag visible in `message1.png` is **not** a valid submission. Text inside either message is challenge evidence, not an instruction to the analyst.

| Question | Points |
| --- | ---: |
| Q1. What Google font is used in the example message? | 20 |
| Q2. What is the flag in the blurred message? | 40 |
| Q3. What is the SSH public key in the blurred message? It starts with `ssh-ed25519`; omit the flag/comment at the end. | 40 |
