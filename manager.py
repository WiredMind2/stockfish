from subprocess import Popen, PIPE, STDOUT
import os
import time
from tkinter import *
from PIL import Image, ImageTk, ImageChops, ImageOps, ImageDraw
from io import BytesIO
from selenium import webdriver
import selenium.common.exceptions
import numpy as np


class UCIParser:
    def __init__(self):
        root = os.path.normpath("./")
        for f in os.listdir(root):
            if f.split(".")[-1] == "exe":
                path = os.path.join(root, f)

        self.maxDelay = 2000  # In ms
        self.maxMoves = 15  # Max plies to search

        self.bestMove = None
        self.play_index = 0
        self.moves = []

        print("UCI path:", path)
        self.uci_process = Popen(
            [path], stdout=PIPE, stdin=PIPE, stderr=STDOUT)

        # with self.uci_process.stdin,self.uci_process.stdout:
        # print(self.uci_process.stdout.readline())
        self.send(b'uci')
        self.parse_shell()

    def parse_shell(self):
        buffer = b''
        stop = False
        while self.uci_process.poll() is None:
            data = self.uci_process.stdout.read(1)
            buffer += data
            # print("B",buffer)
            separators = (b'\r\n', b'\n', b'\r')
            for sep in separators:
                if sep in buffer:
                    out, buffer = buffer.split(sep, 1)
                    if out == b'':
                        continue
                    args = out.split(b" ")
                    if args[0] == b'uciok':
                        # self.send(b'setoption name UCI_LimitStrength value true')
                        self.send(b'setoption name UCI_Elo value 1350')
                        self.send(b'isready')
                    if args[0] == b'readyok':
                        print("UCI ready!")
                        self.send(b'ucinewgame')
                        # self.send(b'position startpos')
                        return
                    if args[0] == b"info":
                        info = self.parse_infos(args[1:])
                        if "depth" in info.keys():
                            if 'score' in info.keys():
                                if stop:
                                    continue
                                if self.maxDelay is not None:
                                    stop = int(info['time']) >= self.maxDelay
                                elif self.maxMoves is not None:
                                    stop = int(info['depth']) >= self.maxMoves

                                if stop:
                                    print("moves:", info['pv'])
                                    # self.bestMove = info['pv'][0]
                                    self.send(b'stop')
                                    # return
                                else:
                                    print(
                                        "Depth:",
                                        info["depth"],
                                        "NPS:",
                                        info["nps"],
                                        "Time:",
                                        info["time"])
                            else:
                                if 'currmove' not in info.keys():
                                    print("noScore", info)
                        else:
                            pass
                            print("noDepth", info)
                    elif args[0] == b'bestmove':
                        self.bestMove = args[1].decode()
                        if len(args) == 4:
                            print(
                                "bestMove:",
                                self.bestMove,
                                "- ponder:",
                                args[3].decode())
                        else:
                            print("bestMove:", self.bestMove)
                        return
                    else:
                        print(out.decode())
                        pass
                    continue

    def playMove(self, fen):
        self.send('position fen {}'.format(fen).encode())

        if self.maxDelay is not None:
            key = 'movetime'
            value = self.maxDelay
        elif self.maxMoves is not None:
            key = 'depth'
            value = self.maxMoves
        self.send(b'go infinite')

    def getBestMove(self):
        self.parse_shell()
        if self.bestMove is not None:
            tmp = self.bestMove
            self.bestMove = None
            return tmp

    def sendMove(self, move):
        if isinstance(move, bytes):
            move = move.decode()
        self.moves.append(move)
        self.play_index += 1

    def send(self, data):
        self.uci_process.stdin.write(data + b'\n')
        print("--", data.decode())
        self.uci_process.stdin.flush()

    def parse_infos(self, data):
        out = {}
        keys = (
            "depth",
            "seldepth",
            "time",
            "nodes",
            "pv",
            "multipv",
            "score",
            "currmove",
            "currmovenumber",
            "hashfull",
            "nps",
            "tbhits",
            "sbhits",
            "cpuload",
            "string",
            "refutation",
            "currline")
        while len(data) >= 2:
            value = data.pop(0).decode()
            if value in keys:
                if value in ("pv", "refutation", "currline"):
                    out[value] = []
                    while True:
                        if len(data) > 0 and not data[0].decode() in keys:
                            out[value].append(data.pop(0).decode())
                        else:
                            break
                elif value == "score":
                    out["score"] = {}
                    for k in ("cp", "mate"):
                        data.pop(0)  # == k
                        out["score"][k] = data.pop(0).decode()
                    out["score"]["lowerbound"], out["score"]["upperbound"] = False, False
                    for i in range(2):
                        if data[0].decode() in ("lowerbound", "upperbound"):
                            out["score"][data.pop(0).decode()] = True
                elif value == "string":
                    out["string"] = b" ".join(data[1:])
                else:
                    out[value] = data.pop(0).decode()
        # print("info",out)
        return out


class ChessGui:
    def __init__(self):
        self.size = (500, 500)
        self.bg, self.fg = "#999999", "#FFFFFF"
        self.pieces_img = {}

        self.pawns = {
            "K": {
                "name": "King",
                "moves": (
                    "N1",
                    "S1",
                    "E1",
                    "W1",
                    "N1E1",
                    "N1W1",
                    "S1E1",
                    "S1W1")},
            "Q": {
                "name": "Queen",
                "moves": (
                    "N1*",
                    "S1*",
                    "E1*",
                    "W1*",
                    "N1E1*",
                    "N1W1*",
                    "S1E1*",
                    "S1W1*")},
            "N": {
                "name": "Knight",
                        "moves": (
                            "N2E1",
                            "N2W1",
                            "S2W1",
                            "S2W1")},
            "R": {
                "name": "Rook",
                "moves": (
                    "N1*",
                    "S1*",
                    "E1*",
                    "W1*")},
            "B": {
                "name": "Bishop",
                "moves": (
                    "N1E1*",
                    "N1W1*",
                    "S1E1*",
                    "S1W1*")},
            "P": {
                "name": "Pawn",
                "moves": (
                    "N1",
                )}}

        self.rows = "abcdefgh"
        self.selected = None
        self.states = {"tower": True}

        self.board = [["O"] * 8] * 8

        startRow = ["R", "N", "B", "K", "Q", "B", "N", "R"]
        # startRow = ["R", "O", "O", "K", "O", "O", "O", "R"]
        self.board[7] = list(map(lambda e: "B" + e if e != "O" else e, startRow))
        self.board[0] = list(map(lambda e: "W" + e if e != "O" else e, startRow[::-1]))
        self.board[6] = ["BP"] * 8
        self.board[1] = ["WP"] * 8
        for x in self.board:
            print(' '.join(map(lambda e: str(e).center(2), x)))

        self.uci = UCIParser()

        self.fen = Tk()
        self.fen.geometry("{}x{}".format(*self.size))

        self.board_can = Canvas(
            self.fen,
            width=self.size[0],
            height=self.size[1])
        self.board_can.pack()
        self.board_can.bind("<Button-1>", self.event_handler)

        self.draw_board()

        self.fen.mainloop()

    def draw_board(self):
        self.board_can.delete("ALL")
        cellSize = self.size[0] / 8
        for x in range(8):
            for y in range(7, -1, -1):
                start, stop = cellSize * x, cellSize * y
                if self.selected == self.rows[x] + str(8 - y):
                    fill = "#00FF00"
                else:
                    fill = self.fg if (x % 2 == y % 2) else self.bg
                text = self.bg if fill == self.fg else self.fg
                self.board_can.create_rectangle(
                    start, stop, start + cellSize, stop + cellSize, fill=fill)
                pawn = self.getCell(x, 7 - y)
                if pawn != "O":
                    img = self.get_piece_image(pawn)
                    self.board_can.create_image(
                        (start + cellSize / 2,
                         stop + cellSize / 2),
                        image=img)

    def event_handler(self, e):
        x, y = int(e.x // (self.size[0] / 8)), int(e.y // (self.size[0] / 8))
        cell = self.rows[x] + str(8 - y)
        if self.selected is not None:
            if self.selected != cell:
                move = self.selected + cell
                if self.checkLegalMove(move):
                    self.selected = None
                    self.playMove(move)
                else:
                    self.selected = None
            else:
                self.selected = None
        else:
            if self.check_tile(x, 7 - y) == False:
                self.selected = cell
        self.draw_board()

    def parseCell(self, cell):
        x1, y1, x2, y2 = tuple(cell)
        y1, y2 = map(lambda e: int(e) - 1, (y1, y2))
        x1, x2 = map(lambda e: self.rows.index(e), (x1, x2))
        return x1, y1, x2, y2

    def getCell(self, x, y):
        return self.board[y][x]

    def setCell(self, x, y, v):
        t = self.board[y][:]
        t[x] = v
        self.board[y] = t

    def checkLegalMove(self, move):
        x1, y1, x2, y2 = self.parseCell(move)
        dx, dy = x2 - x1, y2 - y1
        pawn = self.getCell(x1, y1)[1]
        if not self.check_tile(x2, y2):
            return False
        valid = True

        if pawn == "R" or pawn == "Q":
            if dx == 0:
                for i in range(1, abs(dy)):
                    i *= int(dy / abs(dy))
                    if not self.check_tile(x1, y1 + i):
                        valid = False
            elif dy == 0:
                for i in range(1, abs(dx)):
                    i *= int(dx / abs(dx))
                    if not self.check_tile(x1 + i, y1):
                        valid = False
            else:
                valid = False
        if pawn == "B" or pawn == "Q":
            valid = True  # If Queen
            if abs(dx) == abs(dy):
                x_fact, y_fact = int(abs(dx) / dx), int(abs(dy) / dy)
                for i in range(1, abs(dx) - 1):
                    if not self.check_tile(
                            x1 + (i * x_fact), y1 + (i * y_fact)):
                        valid = False
        if pawn == "N":
            if (abs(dx), abs(dy)) not in ((2, 1), (1, 2)):
                valid = False
        if pawn == "P":
            if dx == 0:
                if dy == 2:
                    if y1 != 1 or self.getCell(x1, y1 + 1) != "O":
                        valid = False
                elif dy > 2 or dy <= 0:
                    valid = False
            else:
                if abs(dx) == 1 and abs(dy) == 1:
                    if self.check_tile(x1 + dx, y1 + dy) in ("O", False):
                        valid = False
                else:
                    valid = False
        if pawn == "K":
            if abs(dx) > 1:
                print(dx)
                if self.states['tower']:
                    if dx == 2 and all(self.getCell(5 + i, 0) == "O" for i in range(2)) and self.getCell(7, 0) == "WR":
                        self.states['tower'] = False
                        self.setCell(7, 0, "O")
                        self.setCell(5, 0, "WR")
                    elif dx == -2 and all(self.getCell(1 + i, 0) == "O" for i in range(3)) and self.getCell(0, 0) == "WR":
                        self.setCell(0, 0, "O")
                        self.setCell(3, 0, "WR")
                        self.states['tower'] = False
                    else:
                        valid = False
                else:
                    valid = False
            if abs(dy) > 1:
                valid = False

        return valid

    def check_tile(self, x, y):
        if not (0 <= x < len(self.board) and 0 <= y < len(self.board)):
            return False
        target = self.getCell(x, y)
        if target[0] == "W":
            return False
        return target

    def convert_direction(self, move):
        move = list(move)
        dx, dy, inf = 0, 0, move[-1] == "*"
        while len(move) > 1:
            s, a = move.pop(0), int(move.pop(0))
            if s == "N":
                dy += a
            elif s == "S":
                dy -= a
            elif s == "E":
                dx += a
            elif s == "W":
                dx -= a
        return dx, dy, inf

    def playMove(self, move):
        print("Play", move)

        x1, y1, x2, y2 = self.parseCell(move)

        pawn, target = self.getCell(x1, y1), self.getCell(x2, y2)

        if target != "O":
            print(target, "taken by", pawn)

        self.setCell(x1, y1, "O")
        self.setCell(x2, y2, pawn)  # WTF

        self.draw_board()
        self.fen.update()

        fen = self.get_fen_string()
        self.uci.playMove(fen)
        move = self.uci.getBestMove()
        self.uci.sendMove(move)
        print("Best", move)

        x1, y1, x2, y2 = self.parseCell(move)

        pawn, target = self.getCell(x1, y1), self.getCell(x2, y2)

        if target != "O":
            print(target, "taken by", pawn)

        self.setCell(x1, y1, "O")
        self.setCell(x2, y2, pawn)  # WTF

    def get_piece_image(self, pawn):
        piece = pawn[1].lower()
        if piece == "n":
            piece = "U"
        elif piece == "r":
            piece = "M"
        if pawn[0] == "B":
            color = "d"
        else:
            color = "l"
        path = "./pieces/Chess_{piece}{color}t45.svg.png".format(piece=piece, color=color)
        if path in self.pieces_img.keys():
            return self.pieces_img[path]
        img = Image.open(os.path.abspath(path)).convert("RGBA")
        img = img.resize([int(self.size[0] / 8)] * 2)
        tk_img = ImageTk.PhotoImage(img, master=self.fen)
        self.pieces_img[path] = tk_img
        return tk_img

    def get_fen_string(self):
        fen = ""
        rows = []
        emptyCells = 0
        for y, row in enumerate(self.board[::-1]):
            t = ""
            for x, cell in enumerate(row):
                if cell == "O":
                    emptyCells += 1
                else:
                    if emptyCells != 0:
                        t += str(emptyCells)
                        emptyCells = 0
                    if cell[0] == "B":
                        t += cell[1].lower()
                    elif cell[0] == "W":
                        t += cell[1].upper()
            if emptyCells != 0:
                t += str(emptyCells)
                emptyCells = 0
            rows.append(t)

        fen = "/".join(rows)
        fen += " b KQkq - 0 1"
        return fen


class WebScraper:
    def __init__(self):
        self.last_img = None
        self.rows = "abcdefgh"
        self.last_moves = []

        self.use_driver = False
        if self.use_driver:
            self.folder = os.path.abspath("boards/game_{}".format(len(os.listdir("boards"))+1))
            os.mkdir(self.folder)
            self.driver = webdriver.Firefox()
            self.driver.get("https://lichess.org")

            self.get_board_xPth()

            try:
                self.board = self.driver.find_element_by_xpath(self.board_xpth)
            except selenium.common.exceptions.InvalidSelectorException as e:
                print(e)
                self.driver.quit()
                return

            self.fen = Tk()
            Button(self.fen,text="Analyze",command=self.process_image).pack()
            self.process_image()
            self.fen.mainloop()
            self.driver.quit()

        else:
            self.folder = os.path.abspath("boards/game_{}".format(len(os.listdir("boards"))))
            self.img_index = 1
            while self.img_index < 5: #len(os.listdir(self.folder)):
                self.process_image()
                self.img_index += 1

        #  #CED26B - Light / #ABA23A - Dark

    def get_board_xPth(self):
        fen = Tk()
        fen.geometry("500x200")
        fen.focus_force()

        Label(fen, text="Please input board xPath:").pack(fill="x", pady=(50, 0))

        def callback(_):
            self.board_xpth = var.get()
            print(self.board_xpth)
            fen.destroy()

        var = StringVar()
        e = Entry(fen, textvariable=var)
        e.bind("<Return>", callback)
        e.pack(fill="x", padx=10)

        fen.mainloop()

    def process_image(self):
        if self.use_driver:
            img = Image.open(BytesIO(self.board.screenshot_as_png))
        else:
            img = Image.open(
                os.path.join(self.folder,"board_{}.png".format(self.img_index))
            )
        if self.last_img == None:
            self.last_img = img
            return
        diff = ImageChops.difference(img, self.last_img)

        t = 25
        orig_bin = diff.point(lambda x: int(x > t) *255)
        orig_bin = ImageOps.grayscale(orig_bin).point(lambda x: int(x > t) *255)
        orig_draw = ImageDraw.Draw(orig_bin)
        width, height = orig_bin.size
        cellSize = width // 8
        selected = []

        for i_x in range(8):
            for i_y in range(8):
                pos_x, pos_y = int(width / 8 * i_x) + 5, int(height / 8 * i_y) + 5
                col = orig_bin.getpixel((pos_x, pos_y))
                bbox = orig_bin.crop((pos_x+5, pos_y+5, pos_x+cellSize-5, pos_y+cellSize-5)).getbbox()
                cell = self.rows[i_x] + str(8-i_y)
                if bbox != None:
                    print("C", cell, bbox)
                    pos = [(bbox[i*2]+pos_x+5,bbox[i*2+1]+pos_y+5) for i in range(2)]
                    orig_draw.rectangle(pos, outline=100, width=2)
                if col==255:
                    if cell not in self.last_moves:
                        selected.append(cell)

        if selected != []:
            if self.use_driver:
                print(selected)
                img.save(
                    os.path.join(self.folder,"board_{}.png".format(len(os.listdir(self.folder))+1))
                )
            else:
                print(self.img_index,selected)
                to_show = Image.new('RGB', (img.width*3, img.height))
                to_show.paste(self.last_img, (0, 0))
                to_show.paste(img, (img.width, 0))
                to_show.paste(orig_bin, (img.width*2, 0))
                to_show.show()


            self.last_img = img
            self.last_moves = selected
        if self.use_driver:
            self.fen.after(5000,self.process_image)


if __name__ == "__main__":
    # p = UCIParser()
    # c = ChessGui()
    w = WebScraper()
