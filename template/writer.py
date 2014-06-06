import struct
def writer(filename, image, size):
    formats = {
        'Buint32': '>I',
        'Buint64': '>Q',
        'Bchar32': '>4s'
    }

    fd = open(filename, 'w+')
    fd.seek(size)
    fd.write("\0")

    for field in image:
        print field
        fd.seek(field[0])
        fd.write(struct.pack(formats[field[2]], field[1]))

    fd.close()
