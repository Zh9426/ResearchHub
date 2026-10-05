"""Deterministic PWA PNGs matching the committed vector icon; no external assets."""
import math,struct,zlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'public'/'icons'
def png(size):
    rows=[]
    for y in range(size):
        row=bytearray()
        for x in range(size):
            px=(x+.5)*512/size-256;py=(y+.5)*512/size-256
            white=px*px+py*py<24*24
            for angle in (0,math.pi/3,2*math.pi/3):
                u=px*math.cos(angle)+py*math.sin(angle);v=-px*math.sin(angle)+py*math.cos(angle)
                radius=(u/174)**2+(v/66)**2
                # Approximate 16px stroke by distance to ellipse.
                grad=2*math.sqrt((u/174**2)**2+(v/66**2)**2)
                white|=bool(grad and abs(radius-1)/grad<8)
            row.extend((255,255,255) if white else (17,107,102))
        rows.append(b'\0'+row)
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
for size in (192,512):(root/f'icon-{size}.png').write_bytes(png(size))
