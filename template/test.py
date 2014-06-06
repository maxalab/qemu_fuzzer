import qcow2
import writer


if __name__ == '__main__':
    temp = {}
    temp['header'] = {}
    for v in qcow2.qcow2['header']:
        temp['header'][v] = {}
        temp['header'][v]['value'] = qcow2.qcow2['header'][v].value(temp)
        print str(v) + " value " + str(temp['header'][v]['value'])
        temp['header'][v]['offset'] = qcow2.qcow2['header'][v].offset(temp)
        print str(v) + " offset " + str(temp['header'][v]['offset'])
        temp['header'][v]['size'] = qcow2.qcow2['header'][v].size
        print str(v) + " size " + str(temp['header'][v]['size'])
        temp['header'][v]['format'] = qcow2.qcow2['header'][v].fmt
        print str(v) + " format " + str(temp['header'][v]['format'])

    flat = [[v['offset'], v['value'], v['format']] for v in \
            temp['header'].values()]

    writer.writer('/tmp/test.img', flat, 2**20)
