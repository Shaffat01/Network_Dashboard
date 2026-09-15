import paramiko
import socket
import time
import re

IP = "192.168.101.248" # CBS350 Switch
USER = "root"
PASS = "WhqAcc*&^8u7y"

print("=" * 60)
print(f"Testing Keyboard-Interactive SSH to {IP}")
print("=" * 60)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect((IP, 22))

transport = paramiko.Transport(sock)
opts = transport.get_security_options()
opts.key_types = ('ssh-rsa', 'ssh-dss')
opts.ciphers = ('aes128-cbc', 'aes192-cbc', 'aes256-cbc', '3des-cbc', 'aes128-ctr', 'aes192-ctr', 'aes256-ctr')
opts.kex = ('diffie-hellman-group1-sha1', 'diffie-hellman-group14-sha1', 'diffie-hellman-group-exchange-sha1')

transport.start_client()

authenticated = False

# 1. Keyboard-Interactive Auth (PuTTY Style)
try:
    def kb_handler(title, instructions, prompt_list):
        answers = []
        for prompt, echo in prompt_list:
            answers.append(PASS)
        return answers

    transport.auth_interactive(USER, kb_handler)
    authenticated = True
    print("✅ Authenticated via Keyboard-Interactive Mode!")
except Exception as e:
    print("Keyboard-Interactive notice:", e)

# 2. Shell Auth Fallback
if not authenticated:
    try:
        transport.auth_none(USER)
        authenticated = True
        print("✅ Authenticated via auth_none!")
    except Exception as e:
        try:
            transport.auth_none('')
            authenticated = True
            print("✅ Authenticated via auth_none('')!")
        except Exception:
            pass

# Open Interactive Shell
channel = transport.open_session()
channel.get_pty(term='vt100', width=160, height=100)
channel.invoke_shell()

time.sleep(2)
out = ""
if channel.recv_ready():
    out += channel.recv(8192).decode('utf-8', errors='ignore')

clean_out = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', out)

# Handle Terminal Prompts
if "User Name:" in clean_out or "login" in clean_out.lower() or "User:" in clean_out:
    channel.send(USER + "\n")
    time.sleep(1)
    channel.send(PASS + "\n")
    time.sleep(2)

channel.send("\n")
time.sleep(1)
if channel.recv_ready():
    out += channel.recv(8192).decode('utf-8', errors='ignore')

clean_out = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', out)

if "#" in clean_out or ">" in clean_out:
    print("\n🎉 SUCCESS! Connected to CBS350 CLI Shell!")
    print("Prompt Output:\n", clean_out[:200])
else:
    print("\n❌ Failed to reach prompt. Output:", clean_out)

transport.close()
print("=" * 60)