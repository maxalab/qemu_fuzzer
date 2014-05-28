import struct

def create_image(name, size):
    '''Create a fully-allocated raw image with sector markers
    Note: The function is temporarily copy-pasted from iotests.py
    '''
    file = open(name, 'w')
    i = 0
    while i < size:
        sector = struct.pack('>l504xl', i / 512, i / 512)
        file.write(sector)
        i = i + 512
    file.close()
    # Verification of logging functionality
    return hash(int)
