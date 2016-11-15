'''
 Known bugs:
    - Incoming message overwrites the text being typed;
    - !kick causes exception because of nothing to read from the client. Here: data = await reader.readuntil();
'''


import asyncio
import re
import hashlib
import datetime

peers = {}

help_message_user = "\t!list \tlist chat room members\r\n" \
                    "\t!quit \tleave this chat\r\n" \
                    "\t!help \tthis help\r\n ".encode()

help_message_admin = help_message_user + "-------------\r\n" \
                                         "\t!kick nickname [reason]\tkick user by nickname with optional " \
                                         "reason message\r\n".encode()

auth_user = {'admin': 'c09ccadebf4dba75c9b677b26ff7ed496e7c08c4152ff220cc0e9535cab84e03e7b07a4848fef4b9f08d2dd97148f18'
                      '96d1d862cae6f42e0ec5f8f731ccbe15f'}

CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"
CURSOR_DOWN_ONE = "\x1b[1B"


class Peer(object):
    def __init__(self, nickname, reader, writer):
        self.nickname = nickname
        self.reader = reader
        self.writer = writer

    def __str__(self):
        return self.nickname


async def message_broadcast(peers, from_peer=None, message="", service=0):
    for peer in peers:
        #peer.writer.write("\x1b[6n\r\n".encode())
        #cursor_position = await peer.reader.readexactly(10)
        if service == 0:
            text = "%s\r<<< %s :: %s :: %s\r\n>>> " % (CURSOR_UP_ONE, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), from_peer,
                                                     message)

            #restore_cursor = ("\x1b[%s;%sf" % (cursor_position[3:5], cursor_position[6])).encode()
            #peer.writer.write(restore_cursor)
        else:
            text = "\r%s\r\n>>> " % message
        peer.writer.write(text.encode())
        await peer.writer.drain()


async def admin_auth(reader, writer):
    for j in range(3):
        writer.write("AUTH: Please authenticate\r\nPassword: ".encode())
        pwd = await reader.readuntil()
        pwd = pwd.strip()
        if auth_user["admin"] == hashlib.sha512(pwd).hexdigest():
            # allow multiple logins for admin
            if "admin" not in peers:
                peers["admin"] = Peer(nickname="admin", reader=reader, writer=writer)
                writer.write("AUTH: Successfully authenticated\r\n".encode())
                return
        else:
            if j == 2:
                writer.write("AUTH: Too much fails. Disconnecting...\r\n".encode())
                writer.close()
            writer.write("AUTH: Authentication failed. Try again\r\n".encode())
            await asyncio.sleep(1.0)


async def kick_peer(nickname, reason="No reason"):
    try:
        peer = peers[nickname]
        m = ("\rINFO: Admin kicked you from this room. Reason: %s\r\n" % reason).encode()
        peer.writer.write(m)
        peer.writer.close()
        del peers[nickname]
        peers["admin"].writer.write("INFO: OK\r\n".encode())
    except:
        peers["admin"].writer.write("INFO: No such user\r\n".encode())
    finally:
        return


async def main_loop(reader, writer):
    while True:
        writer.write("INFO: Enter your nickname: ".encode())
        nickname = await reader.readuntil()
        nickname = (nickname.strip()).decode()
        if re.match("^[0-9A-Za-z]*$", nickname):
            if nickname == "admin":
                await admin_auth(reader, writer)
                break
            elif nickname not in peers:
                peers[nickname] = Peer(nickname=nickname, reader=reader, writer=writer)
                break
            else:
                writer.write("ERROR: This name is already in use. Pick another\r\n".encode())
        else:
            writer.write("ERROR: Allowed symbols in nickname are letters and digits\r\n".encode())
    writer.write("INFO: Start messaging...\r\n".encode())
    writer.write("INFO: Type !help to get some help\r\n".encode())
    broadcast_to = [v for k, v in peers.items() if k != nickname]
    await message_broadcast(broadcast_to, message="INFO: %s joined the chat" % nickname, service=1)

    while True:
        writer.write("\r>>> ".encode())
        data = await reader.readuntil()
        message = (data.strip()).decode()
        writer.write((CURSOR_UP_ONE + ERASE_LINE).encode())
        line = ("\r>>> %s :: %s :: %s\r\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), nickname,
                                              message)).encode()
        writer.write(line)
        if message != "":
            # service message
            if message[0] == "!":
                if message == "!help":
                    writer.write(help_message_admin) if nickname == "admin" else writer.write(help_message_user)
                elif message == "!list":
                    writer.write("".join(["%s\r\n" % k for k, v in peers.items()]).encode())
                elif message[:5] == "!kick" and nickname == "admin":
                    m = message.split()
                    if len(m) > 1:
                        peer = m[1]
                        try:
                            if m[2]:
                                reason = " ".join([w for w in m[2:]])
                                await kick_peer(peer, reason=reason)
                        except IndexError:
                            await kick_peer(peer)
                elif message == "!quit":
                    writer.write("INFO: See you soon...Disconnecting".encode())
                    broadcast_to = [v for k, v in peers.items() if k != nickname]
                    await message_broadcast(broadcast_to, message="INFO: %s decided to leave the room" % nickname,
                                            service=1)
                    writer.close()
                    del peers[nickname]
                    return
                else:
                    writer.write("ERROR: No such command\r\n".encode())

            # ordinary message
            else:
                broadcast_to = [v for k, v in peers.items() if k != nickname]
                await message_broadcast(broadcast_to, nickname, message)


loop = asyncio.get_event_loop()
coro = asyncio.start_server(main_loop, '0.0.0.0', 8888, loop=loop)
server = loop.run_until_complete(coro)

# Serve requests until Ctrl+C is pressed
print('Serving on {}'.format(server.sockets[0].getsockname()))
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

# Close the server
server.close()
loop.run_until_complete(server.wait_closed())
loop.close()
