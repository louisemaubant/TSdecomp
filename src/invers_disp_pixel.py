#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

################################################################################
# Author        : Simon DAOUT
################################################################################

"""\
invers_disp_pixel.py
-------------
Temporal inversions of the time series delays of selected pixels (used depl_cumule (BIP format) and images_retenues, output of invers_pixel).

Usage: invers_disp_pixel.py --cols=<values> --ligns=<values> [--cube=<path>] [--list_images=<path>] [--windowsize=<value>] [--windowrefsize=<value>]  [--lectfile=<path>] [--aps=<path>] \
[--rmspixel=<path>] [--interseismic=<value>] [--threshold_rmsd=<value>] [--coseismic=<value>] [--postseismic=<value>] [--seasonal=<yes/no>] [--vector=<path>]\
[--semianual=<yes/no>]  [--dem=<yes/no>] [--imref=<value>] [--cond=<value>] [--slowslip=<value>] [--ineq=<value>] \
[--name=<value>] [--rad2mm=<value>] [--plot=<yes/no>] [<iref>] [<jref>] [--bounds=<value>]

invers_disp_pixel.py -h | --help
Options:

-h --help               Show this screen
--ncols VALUE           Pixel column numbers (eg. 200,400,450)
--nligns VALUE          Pixel lign numbers  (eg. 1200,1200,3000)
--cube PATH             Path to displacement file [default: depl_cumul_flat]
--list_images PATH      Path to list images file made of 4 columns containing for each images 1) number 2) date in YYYYMMDD format 3) numerical date 4) perpendicular baseline [default: images_retenues]
--windowsize VALUE      Number of pixels around the pixel defining the window [default: 0]
--windowref size VALUE      Number of pixels around the referenced pixel defining the window [default: windowsize]
--lectfile PATH         Path to the lect.in file (output of invers_pixel) [default: lect.in]
--aps PATH              Path to the APS file giving the error associated to each dates [default: No weigthing]
--rmspixel PATH         Path to the RMS map giving the error associated to each pixel (e.g RMSpixel, output of invers_pixel) [default: None]
--interseismic PATH     Add a linear function to the inversion
--threshold_rmsd VALUE  If interseismic = yes: first try inversion with ref/interseismic/dem only, if RMDS inversion > threshold_rmsd then add other
basis functions [default: 1.]
--coseismic PATH        Add heaviside functions to the inversion .Indicate coseismic time (e.g 2004.,2006.)
--postseismic PATH      Add logarithmic transients to each coseismic step. Indicate characteristic time of the log function, must be a serie of values
of the same lenght than coseismic (e.g 1.,1.). To not associate postseismic function to a given coseismic step, put None (e.g None,1.)
--slowslip   VALUE      Add slow-slip function in the inversion (as defined by Larson et al., 2004). Indicate median and characteristic time of the events
(e.g. 2004.,1,2006,0.5), default: None
--seasonal PATH         If yes, add seasonal terms in the inversion
--semianual PATH        If yes, add semianual  terms in the inversion
--vector PATH           Path to the vector text file containing a value for each dates [default: None]
--dem PATH              If yes, add term proportional to the perpendicular baseline in the inversion
--imref VALUE           Reference image number [default: 1]
--cond VALUE            Condition value for optimization: Singular value smaller than cond*largest_singular_value are considered zero [default: 1.0e-10]
--ineq VALUE            If yes, add inequqlity constrained in the inversion: use least square result to iterate the inversion. Force postseismic to be the
same sign than coseismic [default: no].
--name Value            Name output figures [default: None]
--rad2mm                Scaling value between input data (rad) and desired output [default: -4.4563]
--plot                  Display results [default: yes]
--iref                  colum numbers of the reference pixel [default: None]
--jref                  lign number of the reference pixel [default: None]
--bounds                Min,Max time series plots
"""

# numpy
import numpy as np
from numpy.lib.stride_tricks import as_strided

# scipy
import scipy
import scipy.optimize as opt
import scipy.linalg as lst

# basic
import math,sys,getopt
from os import path, environ
import os

# plot
import matplotlib
if environ["TERM"].startswith("screen"):
    matplotlib.use('Agg')
from pylab import *
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.dates as mdates
from datetime import datetime
import datetime
import time

# docopt (command line parser)
from nsbas import docopt


########################################################################
# Define basis functions
########################################################################


class pattern:
    def __init__(self,name,reduction,date):
        self.name=name
        self.reduction=reduction
        self.date=date

    def info(self):
        print self.name, self.date

def Heaviside(t):
        h=np.zeros((len(t)))
        h[t>=0]=1.0
        return h

class coseismic(pattern):
      def __init__(self,name,reduction,date):
          pattern.__init__(self,name,reduction,date)
          self.to=date

      def g(self,t):
        return (Heaviside(t-self.to))

class postseismic(pattern):
      def __init__(self,name,reduction,date,tcar=1):
          pattern.__init__(self,name,reduction,date)
          self.to=date
          self.tcar=tcar

      def g(self,t):
        t=(t-self.to)/self.tcar
        t[t<=0] = 0
        g = np.log10(1+t)
        return g

class reference(pattern):
    def __init__(self,name,reduction,date):
        pattern.__init__(self,name,reduction,date)
    def g(self,t):
        return np.ones((t.size))

class interseismic(pattern):
    def __init__(self,name,reduction,date):
        pattern.__init__(self,name,reduction,date)
        self.to=date

    def g(self,t):
        func=(t-self.to)
        return func

class sinvar(pattern):
    def __init__(self,name,reduction,date):
        pattern.__init__(self,name,reduction,date)
        self.to=date

    def g(self,t):
        func=np.zeros(t.size)
        for i in xrange(t.size):
            func[i]=math.sin(2*math.pi*(t[i]-self.to))
        return func

class cosvar(pattern):
    def __init__(self,name,reduction,date):
        pattern.__init__(self,name,reduction,date)
        self.to=date

    def g(self,t):
        func=np.zeros(t.size)
        for i in xrange(t.size):
            func[i]=math.cos(2*math.pi*(t[i]-self.to))
        return func

class sin2var(pattern):
    def __init__(self,name,reduction,date):
        pattern.__init__(self,name,reduction,date)
        self.to=date

    def g(self,t):
        func=np.zeros(t.size)
        for i in xrange(t.size):
            func[i]=math.sin(4*math.pi*(t[i]-self.to))
        return func

class cos2var(pattern):
    def __init__(self,name,reduction,date):
        pattern.__init__(self,name,reduction,date)
        self.to=date

    def g(self,t):
        func=np.zeros(t.size)
        for i in xrange(t.size):
            func[i]=math.cos(4*math.pi*(t[i]-self.to))
        return func

class slowslip(pattern):
      def __init__(self,name,reduction,date,tcar=1):
          pattern.__init__(self,name,reduction,date)
          self.to=date
          self.tcar=tcar

      def g(self,t):
          t=(t-self.to)/self.tcar
          funct = 0.5*(np.tanh(t)-1) + 1
          return funct

### KERNEL FUNCTIONS: not function of time
class corrdem(pattern):
    def __init__(self,name,reduction,bp0,bp):
        self.name = name
        self.reduction = reduction
        self.bpo=bp0
        self.bp=bp

    def info(self):
        print self.name

    def g(self,index):
        func = (self.bp-self.bpo)
        return func[index]

class vector(pattern):
    def __init__(self,name,reduction,vec):
        self.name = name
        self.reduction = reduction
        self.func=vec

    def info(self):
        print self.name

    def g(self,index):
        return self.func[index]


########################################################################

# read arguments
arguments = docopt.docopt(__doc__)

# initialise iteration with interseismic alone
iteration=False

if arguments["--list_images"] ==  None:
    listim = "images_retenues"
else:
    listim = arguments["--list_images"]

if arguments["--ineq"] ==  None:
    ineq = 'no'
else:
    ineq = arguments["--ineq"]
if arguments["--cond"] ==  None:
    rcond = 1.0e-10
else:
    rcond = float(arguments["--cond"])
if arguments["--imref"] ==  None:
    imref = 0
else:
    imref = int(arguments["--imref"]) - 1
if arguments["--cube"] ==  None:
    cubef = "depl_cumule"
else:
    cubef = arguments["--cube"]
if arguments["--lectfile"] ==  None:
    infile = "lect.in"
else:
    infile = arguments["--lectfile"]
if arguments["--windowsize"] ==  None:
    w = 0
else:
    w = int(arguments["--windowsize"])
if arguments["--windowrefsize"] ==  None:
    wref = np.copy(w)
else:
    wref = int(arguments["--windowrefsize"])

if arguments["--aps"] ==  None:
    apsf = None
else:
    apsf = arguments["--aps"]
if arguments["--rmspixel"] ==  None:
    rmsf = None
else:
    rmsf = arguments["--rmspixel"]
if arguments["--interseismic"] ==  None:
    inter = 'no'
else:
    inter = arguments["--interseismic"]
if arguments["--seasonal"] ==  None:
    seasonal = 'no'
else:
    seasonal = arguments["--seasonal"]
if arguments["--semianual"] ==  None:
    semianual = 'no'
else:
    semianual = arguments["--semianual"]
if arguments["--dem"] ==  None:
    dem = 'no'
else:
    dem = arguments["--dem"]
if arguments["--coseismic"] ==  None:
    cos = []
else:
    cos = map(float,arguments["--coseismic"].replace(',',' ').split())
if arguments["--postseismic"] ==  None:
    pos = []
else:
    pos = map(float,arguments["--postseismic"].replace('None','-1').replace(',',' ').split())

if arguments["--slowslip"] == None:
    sse=[]
else:
    sse = map(float,arguments["--slowslip"].replace(',',' ').split())
sse_time = sse[::2]
sse_car = sse[1::2]

if arguments["--vector"] != None:
    vect = arguments["--vector"]
else:
    vect = None

if arguments["--bounds"] is not  None:
    ylim = map(float,arguments["--bounds"].replace(',',' ').split())

if arguments["<iref>"] ==  None:
    iref = None
else:
    iref = int(arguments["<iref>"])
if arguments["<jref>"] ==  None:
    jref = None
else:
    jref = int(arguments["<jref>"])

if arguments["--name"] ==  None:
    output = None
else:
    output = arguments["--name"]

if arguments["--threshold_rmsd"] ==  None:
    maxrmsd = 1.
else:
    maxrmsd = float(arguments["--threshold_rmsd"])

if arguments["--rad2mm"] ==  None:
    rad2mm = -4.4563
else:
    rad2mm = float(arguments["--rad2mm"])

if arguments["--plot"] ==  None:
    plot = 'yes'
else:
    plot = arguments["--plot"]

if len(pos)>0 and len(cos) != len(pos):
    raise Exception("coseimic and postseismic lists are not the same size")


ipix = map(int,arguments["--cols"].replace(',',' ').split())
jpix = map(int,arguments["--ligns"].replace(',',' ').split())
if len(jpix) != len(ipix):
   raise Exception("ncols and nligns lists are not the same size")
# number of pixels
Npix = len(ipix)

# read lect.in
ncol, nlign = map(int, open(infile).readline().split(None, 2)[0:2])

# load images_retenues file
nb,idates,dates,base=np.loadtxt(listim, comments='#', usecols=(0,1,3,5), unpack=True,dtype='i,i,f,f')
datemin, datemax = np.int(np.min(dates)), np.int(np.max(dates))+1
N = len(dates)

# lect cube
# ATTENTION: here i convert rad to mm
cubei = np.fromfile(cubef,dtype=np.float32)*rad2mm
cube = as_strided(cubei[:nlign*ncol*N])
print 'Number of line in the cube: ', cube.shape
kk = np.flatnonzero(np.logical_or(cube==9990, cube==9999))
cube[kk] = float('NaN')
maps = cube.reshape((nlign,ncol,N))
print 'Reshape cube: ', maps.shape

# plt.imshow(maps[:,:,-1],vmax=np.nanpercentile(maps[:,:,-1],50))
# plt.show()
# sys.exit()

# set to NaN lakes and ocean, new image ref.
cst = np.copy(maps[:,:,imref])
for l in xrange((N)):
    d = as_strided(maps[:,:,l])
    maps[:,:,l] = maps[:,:,l] - cst

# get some info about the cube
# print np.nanmedian(cube), np.nanmax(cube), np.nanmin(cube)
# print np.nanpercentile(cube,95),np.nanpercentile(cube,5)
# maxrmsd = np.nanpercentile(cube,85) - np.nanmedian(cube)

# arbitrary set the max rms at pi/2
if len(cos) > 0:
    print
    print 'Define a maximal RMSD for adding coseismic and postseismic basis functions in the inversion'
    print 'Max RMSD:',  maxrmsd
    print

# perp baseline term
base_moy = np.mean(base)

if apsf is not None:
    inaps=np.loadtxt(apsf, comments='#', unpack=True,dtype='f')*rad2mm
    print 'Input uncertainties:', inaps
    print 'Set very low values to the 2 percentile to avoid overweighting...'
    # maxinaps = np.nanmax(inaps)
    # inaps= inaps/maxinaps

    minaps= np.nanpercentile(inaps,2)
    index = flatnonzero(inaps<minaps)
    inaps[index] = minaps
    print 'Output uncertainties for first iteration:', inaps


if rmsf is not None:
    rmsmap = np.fromfile(rmsf,dtype=np.float32).reshape((nlign,ncol))*rad2mm
    kk = np.nonzero(np.logical_or(rmsmap==0.0, rmsmap==9999))
    rmsmap[kk] = float('NaN')

if vect is not None:
    v = np.loadtxt(vect, comments='#', unpack = False, dtype='f')

# plot pixels on map
fig, ax = subplots(1)
vmax = np.nanmean(maps[:,:,-1]) + 1.*np.nanstd(maps[:,:,-1])
vmin = np.nanmean(maps[:,:,-1]) - 1.*np.nanstd(maps[:,:,-1])
ax.imshow(maps[:,:,-1], vmax=vmax, vmin=vmin, alpha=0.6)
ax.scatter(ipix,jpix,marker='x',color='black',s=15.)
ax.scatter(iref,jref,marker='x',color='red',s=20.)
for i in xrange((Npix)):
    ax.text(ipix[i],jpix[i],i)
plt.suptitle('Black cross: pixels, red cross: reference point')
# plt.savefig('Map_{}.eps'.format(output), format='EPS')
plt.savefig('Map_{}.pdf'.format(output), format='PDF')
# plt.show()
# sys.exit()

# 0
basis=[
      reference(name='reference',date=datemin,reduction='ref'),
      ]
index = len(basis)

if inter=='yes':
      basis.append(interseismic(name='interseismic',reduction='lin',date=datemin))
      # 1
      indexinter=index
      index = index + 1

if seasonal=='yes':
   # 2
   indexseas = index
   basis.append(cosvar(name='seas. var (cos)',reduction='coswt',date=datemin))
   basis.append(sinvar(name='seas. var (sin)',reduction='sinwt',date=datemin))
   index = index + 2

if semianual=='yes':
   # 4
   indexsemi = index
   basis.append(cos2var(name='semi. annual var (cos)',reduction='cos2wt',date=datemin))
   basis.append(sin2var(name='semi. annual var (sin)',reduction='sin2wt',date=datemin))
   index = index + 2

indexco = np.zeros(len(cos))
for i in xrange(len(cos)):
   # 6
   indexco[i] = int(index)
   basis.append(coseismic(name='coseismic {}'.format(i),reduction='cos{}'.format(i),date=cos[i])),
   index = index + 1
   iteration=True

indexpo = np.zeros(len(pos))
for i in xrange(len(pos)):
   if pos[i] > 0. :
      basis.append(postseismic(name='postseismic {}'.format(i),reduction='post{}'.format(i),date=cos[i],tcar=pos[i])),
      indexpo[i] = int(index)
      index = index + 1

indexsse = np.zeros(len(sse_time))
for i in xrange(len(sse_time)):
    basis.append(slowslip(name='sse {}'.format(i),reduction='sse{}'.format(i),date=sse_time[i],tcar=sse_car[i])),
    indexsse[i] = int(index)
    index = index + 1
    iteration=True

kernels=[]

if dem=='yes':
   kernels.append(corrdem(name='dem correction',reduction='corrdem',bp0=base[imref],bp=base))
   indexdem = index
   index = index + 1

if vect != None:
   kernels.append(vector(name='vector',reduction='vector',vec=v))
   indexvect = index
   index = index + 1

indexpo = indexpo.astype(int)
indexco = indexco.astype(int)
indexsse = indexsse.astype(int)

# define size G matrix
print
Mbasis=len(basis)
print 'Number of basis functions:', Mbasis
Mker=len(kernels)
print 'Number of kernel functions:', Mker
M = Mbasis + Mker
for i in xrange((Mbasis)):
    basis[i].info()

#print indexco, cos
#print indexpo, pos

## inversion procedure
def consInvert(A,b,sigmad,ineq='no',cond=1.0e-10, iter=2000,acc=1e-09):
    '''Solves the constrained inversion problem.

    Minimize:

    ||Ax-b||^2

    Subject to:
    mmin < m < mmax
    '''

    if A.shape[0] != len(b):
        raise ValueError('Incompatible dimensions for A and b')

    if ineq == 'no':

        # build Cov matrix
        Cd = np.diag(sigmad**2,k=0)
        Cov = (np.linalg.inv(Cd))
        # fsoln = np.dot(np.linalg.inv(np.dot(np.dot(A.T,Cov),A)),np.dot(np.dot(A.T,Cov),b))
        try:
            fsoln = np.dot(np.linalg.inv(np.dot(np.dot(A.T,Cov),A)),np.dot(np.dot(A.T,Cov),b))
        except:
            fsoln = lst.lstsq(A,b,cond=cond)[0]
        print 'least-square solution:'
        print fsoln
        print
            # fsoln = np.ones((A.shape[1]))*float('NaN')

    else:

        Ain = np.copy(A)
        bin = np.copy(b)

        ## We here want a solution as much conservatif as possible, ie only coseismic steps
        ## least-squqre solution without post-seismic
        for i in xrange(len(indexco)):
            if pos[i] > 0.:
                Ain[:,indexpo[i]] = 0
        minit = lst.lstsq(Ain,bin,cond=cond)[0]
        print
        print minit

        # # initialize bounds
        mmin,mmax = -np.ones(M)*np.inf, np.ones(M)*np.inf

        # We here define bounds for postseismic to be the same sign than coseismic
        # and coseisnic inferior or egal to the coseimic initial
        for i in xrange(len(indexco)):
            if (pos[i] > 0.) and (minit[int(indexco[i])]>0.):
                mmin[int(indexpo[i])], mmax[int(indexpo[i])] = 0, minit[int(indexco[i])]
                mmin[int(indexco[i])], mmax[int(indexco[i])] = 0, minit[int(indexco[i])]
                if minit[int(indexpo[i])] < 0 :
                    minit[int(indexpo[i])] = 0.
            if (pos[i] > 0.) and (minit[int(indexco[i])]<0.):
                mmin[int(indexpo[i])], mmax[int(indexpo[i])] = minit[int(indexco[i])] , 0
                mmin[int(indexco[i])], mmax[int(indexco[i])] = minit[int(indexco[i])], 0
                if minit[int(indexpo[i])] > 0 :
                    minit[int(indexpo[i])] = 0.

        # print mmin,mmax
        ####Objective function and derivative
        _func = lambda x: np.sum(((np.dot(A,x)-b)/sigmad)**2)
        _fprime = lambda x: 2*np.dot(A.T/sigmad, (np.dot(A,x)-b)/sigmad)

        bounds=zip(mmin,mmax)
        res = opt.fmin_slsqp(_func,minit,bounds=bounds,fprime=_fprime, \
            iter=iter,full_output=True,iprint=0,acc=acc)
        fsoln = res[0]

        print 'optimization:'
        print fsoln
        print
        # sys.exit()

    # tarantola:
    # Cm = (Gt.Cov.G)-1 --> si sigma=1 problems
    # sigma m **2 =  misfit**2 * diag([G.TG]-1)
    try:
       varx = np.linalg.inv(np.dot(A.T,A))
       res2 = np.sum(pow((b-np.dot(A,fsoln)),2))
       scale = 1./(A.shape[0]-A.shape[1])
       # scale = 1./A.shape[0]
       sigmam = np.sqrt(scale*res2*np.diag(varx))
    except:
       sigmam = np.ones((A.shape[1]))*float('NaN')

    print 'model errors:'
    print sigmam

    return fsoln,sigmam

# plot diplacements maps
nfigure = 10
if Npix > 2:
    fig = plt.figure(nfigure+1,figsize=(12,8))
else:
    fig = plt.figure(nfigure+1,figsize=(10,4))
if inter=='yes':
    if Npix > 2:
        fig3 = plt.figure(nfigure+3,figsize=(12,8))
    else:
        fig3 = plt.figure(nfigure+3,figsize=(10,4))
if seasonal == 'yes' or semianual == 'yes':
    if Npix > 2:
        fig2 = plt.figure(nfigure+2,figsize=(12,8))
    else:
        fig2 = plt.figure(nfigure+2,figsize=(10,4))
if vect!=None:
    if Npix > 2:
        fig2 = plt.figure(nfigure+2,figsize=(12,8))
    else:
        fig2 = plt.figure(nfigure+2,figsize=(10,4))


for jj in xrange((Npix)):
    # initialize aps before iterations
    if apsf is None:
        aps = np.ones((N))
    else:
        aps = inaps

    # for ll in xrange(niter):
    i, j = ipix[jj], jpix[jj]
    print
    print '---------------------------------------'
    print 'pixel:{} {}'.format(i,j)
    print '---------------------------------------'
    print

    x = [date2num(datetime.datetime.strptime('{}'.format(d),'%Y%m%d')) for d in idates]
    dmin = str(datemin) + '0101'
    # hardcoding for my plots
    # dmin= 20030101
    dmax = str(datemax) + '0101'
    xmin = datetime.datetime.strptime('{}'.format(dmin),'%Y%m%d')
    xmax = datetime.datetime.strptime('{}'.format(dmax),'%Y%m%d')
    xlim=date2num(np.array([xmin,xmax]))

    # extract data
    wind = as_strided(maps[j-w:j+w+1,i-w:i+w+1,:])
    if iref is not None:
        windref = as_strided(maps[jref-wref:jref+wref+1,iref-wref:iref+wref+1,:])
        dispref = np.nanmean(windref,axis=(0,1))
    else:
        dispref = np.zeros((N))

    disp = np.nanmean(wind,axis=(0,1)) - dispref
    #aps = np.nanstd(wind,axis=(0,1))

    # inversion model
    mdisp= np.ones((N))*float('NaN')
    demerr = np.zeros((N))
    vecteur = np.zeros((N))
    lin = np.zeros((N))
    k = np.flatnonzero(~np.isnan(disp))
    kk = len(k)
    tabx = dates[k]
    taby = disp[k]
    bp = base[k]
    vec = v[k]

    # sigmad = aps
    sigmad = aps  # I don't want zero uncertainties
    print 'data uncertainties', sigmad

    # initialize new aps for each images to 1
    aps = np.ones((N))

    # do only this if more than N/2 points left
    if kk > N/6:
        # Inisilize m
        m,sigmam = np.zeros((M)),np.zeros((M))

        # inversion
        t = time.time()

        rmsd = maxrmsd + 1
        if inter=='yes' and iteration is True:

            Glin=np.zeros((kk,2+Mker))
            for l in xrange((2)):
                Glin[:,l]=basis[l].g(tabx)
            for l in xrange((Mker)):
                Glin[:,2+l]=kernels[l].g(k)

            # print k
            # print sigmad
            # print taby
            mt,sigmamt = consInvert(Glin,taby,sigmad[k],cond=rcond)

            # compute rmsd
            mdisp[k] = np.dot(Glin,mt)

            # rmsd = np.sqrt(np.sum(pow((disp[k] - mdisp[k])/inaps[k],2))/kk)
            rmsd = np.sqrt(np.sum(pow((disp[k] - mdisp[k]),2))/kk)

            print
            print 'rmsd:', rmsd
            print

        G=np.zeros((kk,M))
        for l in xrange((Mbasis)):
            G[:,l]=basis[l].g(tabx)
        for l in xrange((Mker)):
            G[:,Mbasis+l]=kernels[l].g(k)

        if rmsd >= maxrmsd or inter!='yes':
            mt,sigmamt = consInvert(G,taby,sigmad[k],cond=rcond, ineq=ineq)

        # rebuild full vectors
        if Mker>0:
            m[Mbasis:],sigmam[Mbasis:] = mt[-Mker:],sigmamt[-Mker:]
            m[:mt.shape[0]-Mker],sigmam[:mt.shape[0]-Mker] = mt[:-Mker],sigmamt[:-Mker]
        else:
            m [:mt.shape[0]] = mt

        # forward model in original order
        mdisp[k] = np.dot(G,m)
        demerr[k] =  np.dot(G[:,Mbasis:],m[Mbasis:])
        vecteur[k] =  np.dot(G[:,Mbasis:],m[Mbasis:])

        print
        print 'computation time:', time.time() - t
        print


    # plot at the end of iterations for each points
    ax = fig.add_subplot(Npix,1,jj+1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m/%d"))

    if inter=='yes':
        ax3 = fig3.add_subplot(Npix,1,jj+1)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m/%d"))
    if seasonal == 'yes' or semianual == 'yes':
        ax2 = fig2.add_subplot(Npix,1,jj+1)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m/%d"))
    if vect!=None:
        ax2 = fig2.add_subplot(Npix,1,jj+1)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m/%d"))

    # initialize variables
    disp_seas = np.zeros((N))
    disp_vect = np.zeros((N))

    if inter=='yes':
        lin[k] = np.dot(G[:,indexinter],m[indexinter])


    # plot data and model minus dem error
    ax.plot(x,disp-demerr,'o',label='TS {}: lign: {}-{}, column: {}-{}'.format(jj,i-w,i+w,j-w,j+w))
    ax.errorbar(x,disp-demerr,yerr = sigmad, ecolor='blue',fmt='none', alpha=0.5)
    # ax.plot(x,mdisp-demerr,'o', label='model',color='red', alpha=0.5)

    # plot data and model minus dem error and linear term
    if inter=='yes':
        ax3.plot(x,disp-demerr-lin,'o',label='detrended data')
        ax3.errorbar(x,disp-demerr-lin,yerr = sigmad, ecolor='blue',fmt='none', alpha=0.5)
        # ax3.plot(x,mdisp-demerr-lin,'o', label='detrended model',color='red', alpha=0.5)
    # if vect!=None:
    #     ax3.plot(x,disp-demerr-vecteur-lin,'o',label='detrended data')
    #     ax3.errorbar(x,disp-demerr-vecteur-lin,yerr = sigmad, ecolor='blue',fmt='none', alpha=0.5)
    #
    # plot data and model minus dem error and seasonal terms
    if seasonal=='yes':
            G=np.zeros((kk,2))
            for l in xrange((2)):
                G[:,l]=basis[l+indexseas].g(tabx)
            disp_seas[k] = disp_seas[k] + np.dot(G[:,:],m[indexseas:indexseas+2])

    if semianual=='yes':
            G=np.zeros((kk,2))
            for l in xrange((2)):
                G[:,l]=basis[l+indexsemi].g(tabx)
            disp_seas[k] = disp_seas[k] +  np.dot(G[:,:],m[indexsemi:indexsemi+2])

    # if vect!=None:
    #        G=np.zeros((kk,2))
    #        for l in xrange((Mker)):
    #            G[:,l]=kernels[l].g(v)
    #        disp_vec[k] = disp_vec[k] +  np.dot(G[:,:],m[indexvect:indexsemi+2])

    if semianual=='yes' or seasonal=='yes':
        ax2.plot(x,disp-disp_seas-demerr,'o',label='data -seasonal')
        # ax2.plot(x,mdisp-disp_seas-demerr,'o',color='red',alpha=0.5,label='model -seasonal')
        ax2.errorbar(x,disp-disp_seas-demerr,yerr = sigmad, ecolor='blue',fmt='none', alpha=0.3)

    if vect!=None:
        disp_vect[k] =disp_vect[k] + np.dot(G[:,indexvect],m[indexvect])

        ax2.plot(x,disp-vecteur-demerr,'o',label='data -seasonal')
#        ax2.plot(x,vecteur,'o',color='red',alpha=0.5,label='model -seasonal')
        ax2.errorbar(x,disp-disp_vect-demerr,yerr = sigmad, ecolor='blue',fmt='none', alpha=0.3)

    # create synthetic time
    t = np.array([xmin + datetime.timedelta(days=d) for d in range(0, 2920)])
    tdec = np.array([float(date.strftime('%Y')) + float(date.strftime('%j'))/365.1 for date in t])
    mseas = np.zeros(len(tdec))
    model_vect = np.zeros(len(tdec))

    tdec = tabx
    mseas = np.zeros(len(tdec))

    tabx = dates[k]
    new_dt = idates[k]

    temps = [datetime.datetime.strptime('{}'.format(d),'%Y%m%d') for d in new_dt]


    G=np.zeros((len(tabx),M))

    for l in xrange((Mbasis)):
        G[:,l]=basis[l].g(tabx)
    for l in xrange((Mker)):
        G[:,Mbasis+l]=kernels[l].g(k)
        # t = [datetime.datetime.strptime('{}'.format(d),'%Y%m%d') for d in new_dt]

    # correct ??
    model = np.dot(G[:,:],m[:])

    print model.shape
    if inter=='yes':
        model_lin = np.dot(G[:,indexinter],m[indexinter])
    if vect!=None:
        model_vect = np.dot(G[:,indexvect],m[indexvect])
    # plot model

    ax.plot(temps,model,'-r')
    if inter=='yes':
        ax3.plot(temps,model-model_lin,'-r')

    # if vect!=None:
    #     ax2.plot(temps,model-model_vect,'-r')

    if seasonal=='yes':
        G=np.zeros((len(tdec),2))
        for l in xrange((2)):
            G[:,l]=basis[l+indexseas].g(tdec)
        mseas = mseas + np.dot(G[:,:],m[indexseas:indexseas+2])

    if semianual=='yes':
        G=np.zeros((len(tdec),2))
        for l in xrange((2)):
            G[:,l]=basis[l+indexsemi].g(tdec)
        mseas = mseas + np.dot(G[:,:],m[indexsemi:indexsemi+2])

    if seasonal=='yes' or semianual=='yes':
        ax2.plot(temps,model-mseas,'-r')
        ax2.legend(loc='best',fontsize='x-small')
        ax2.set_xlim(xlim)
        if arguments["--bounds"] is not  None:
            ax2.set_ylim(ylim)

    if vect!=None:
        ax2.plot(temps,model-model_vect,'-r')
        ax2.legend(loc='best',fontsize='x-small')
        ax2.set_xlim(xlim)
        if arguments["--bounds"] is not  None:
            ax2.set_ylim(ylim)

    ax.legend(loc='best',fontsize='x-small')
    ax.set_xlim(xlim)
    if arguments["--bounds"] is not  None:
        ax.set_ylim(ylim)

    if inter=='yes':
        ax3.legend(loc='best',fontsize='x-small')
        ax3.set_xlim(xlim)
        if arguments["--bounds"] is not  None:
            ax3.set_ylim(ylim)

    fig.autofmt_xdate()
    ax.set_xlabel('Time (Year/month/day)')
    ax.set_ylabel('Displacements (mm)')
    # fig.savefig('Disp_{}.eps'.format(output), format='EPS')
    fig.savefig('Disp_{}.pdf'.format(output), format='PDF')

    if inter=='yes':
        fig3.autofmt_xdate()
        ax3.set_xlabel('Time (Year/month/day)')
        ax3.set_ylabel('Displacements (mm)')
        # fig3.savefig('Disp_{}_detrended.eps'.format(output), format='EPS')
        fig3.savefig('Disp_{}_detrended.pdf'.format(output), format='PDF')

    if seasonal == 'yes' or semianual =='yes':
        fig2.autofmt_xdate()
        ax2.set_xlabel('Time (Year/month/day)')
        ax2.set_ylabel('Displacements (mm)')
        # fig2.savefig('Disp_{}_deseas.eps'.format(output), format='EPS')
        fig2.savefig('Disp_{}_deseas.pdf'.format(output), format='PDF')

    if vect!=None:
        fig2.autofmt_xdate()
        ax2.set_xlabel('Time (Year/month/day)')
        ax2.set_ylabel('Displacements (mm)')
        # fig2.savefig('Disp_{}_deseas.eps'.format(output), format='EPS')
        fig2.savefig('Disp_{}_devect.pdf'.format(output), format='PDF')


    if seasonal == 'yes':
        cosine = as_strided(m[indexseas])
        sine = as_strided(m[indexseas+1])
        amp = np.sqrt(cosine**2+sine**2)
        phi = np.arctan2(sine,cosine)
        print amp,phi

if plot == 'yes':
    plt.show()
sys.exit()
