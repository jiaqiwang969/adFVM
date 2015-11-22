import numpy as np
import matplotlib.pyplot as plt

plt.rcParams.update({'legend.fontsize': 18,
                     'xtick.labelsize': 16,
                     'ytick.labelsize': 16,
                     'axes.labelsize': 18
                    })

import os

#loc = '/home/talnikar/foam/blade/laminar-lowRe/'
#names = filter(lambda name: name.startswith('adj') and name.endswith('txt'), os.listdir(loc))
#labels = [float(name.split('_')[1].split('.')[0]) for name in names]
#labels, names = zip(*sorted(zip(labels, names)))
#cm = plt.get_cmap('gist_rainbow')
#n = len(names)
#plt.gca().set_color_cycle([cm(1.*i/n) for i in range(n)])
#for name, label in zip(names, labels):
for name,label in zip(['data.txt', 'data2.txt', 'data3.txt'], ['2D adjoint', '3D adjoint', '3D long term adjoint']):
    #if not (name.endswith('.txt') and name.startswith('adj')):
    #    continue
    #f = open(loc + name)
    f = open(name)
    lines = [line for line in f.readlines() if line.startswith('L2 norm adjoint')]
    x = []
    y = []
    for line in lines:
        terms = line.split(' ')
        x.append(float(terms[-2])-3)
        y.append(float(terms[-1]))
    x = x[-1] - np.array(x)
    x /= 0.001
    plt.semilogy(x, y, label=label)#, color=np.random.rand(3,1))
plt.xlabel('Time (T)')
plt.ylabel('Adjoint fields magnitude')
plt.legend(loc=2)
plt.show()


