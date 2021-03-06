#! /usr/bin/env python
import numpy as n, pylab as p, sys, aipy as a, math
import optparse
import qPickle

TRIM = False
#EXP_NOISE = 10.
EXP_NOISE = 1.
#EXP_NOISE = .1

try:
    import fftw3
    print 'Using FFTW FFT'
    _fftw3_dat, _fftw3_fwd, _fftw3_rev = None, None, None
    def fft2(d):
        global _fftw3_fwd, _fftw3_rev, _fftw3_dat
        if not _fftw3_dat is None and _fftw3_dat.shape != d.shape:
            _fftw3_fwd, _fftw3_rev, _fftw3_dat = None, None, None
        if _fftw3_fwd is None:
            if _fftw3_dat is None: _fftw3_dat = n.zeros(d.shape, dtype=n.complex)
            _fftw3_fwd = fftw3.Plan(_fftw3_dat, None, direction='forward', flags=['measure'])
        _fftw3_dat[:] = d
        _fftw3_fwd()
        return _fftw3_dat
    def ifft2(d):
        global _fftw3_fwd, _fftw3_rev, _fftw3_dat
        if not _fftw3_dat is None and _fftw3_dat.shape != d.shape:
            _fftw3_fwd, _fftw3_rev, _fftw3_dat = None, None, None
        if _fftw3_rev is None:
            if _fftw3_dat is None: _fftw3_dat = n.zeros(d.shape, dtype=n.complex)
            _fftw3_rev = fftw3.Plan(_fftw3_dat, None, direction='backward', flags=['measure'])
        _fftw3_dat[:] = d
        _fftw3_rev()
        return _fftw3_dat
except(ImportError):
    print 'Using numpy FFT'
    fft2, ifft2 = n.fft.fft2, n.fft.ifft2

colors = 'kbrgcmy'

o = optparse.OptionParser()
a.scripting.add_standard_options(o, cal=True, pol=True)
o.add_option('-d', '--dw', dest='dw', type=int, default=5,
    help='The number of delay bins to null. If -1, uses baseline lengths to generate a sky-pass filter.')
o.add_option('-r', '--drw', dest='drw', type=int, default=5,
    help='The number of delay-rate bins to null. If -1, uses baseline lengths to generate a sky-pass filter.')
o.add_option('-q', '--quality', dest='quality', default=0., help='Cutoff for plotting a source.')
o.add_option('-b', '--binsize', dest='binsize', default='15',
    help='Number of minutes to include in each LST bin.  Default is 15.')
o.add_option('-S', '--savez', dest='savez', default=False,
    help='Save the results as an npz file.')
o.add_option('-a', '--ant', dest='ant', type=int, default=0,
    help='Which antenna to use in the plot. Default = 0.')
o.add_option('-f', '--freq', dest='freq', type=float, default=.150,
    help='Frequency at which to evaluate the beam in GHz.  Default=.150')
opts, args = o.parse_args(sys.argv[1:])

p.rcParams['legend.fontsize'] = 6

def gen_filter(shape, dw, drw, ratio=.25):
    filter = n.ones(shape)
    x1,x2 = drw, -drw
    if x2 == 0: x2 = shape[0]
    y1,y2 = dw, -dw
    if y2 == 0: y2 = shape[1]
    filter[x1+1:x2,0] = 0
    filter[0,y1+1:y2] = 0
    filter[1:,1:] = 0
    x,y = n.indices(shape).astype(n.float)
    x -= shape[0]/2
    y -= shape[1]/2
    r2 = (x/(ratio*drw+.5))**2 + (y/(ratio*dw+.5))**2
    r2 = a.img.recenter(r2, (shape[0]/2, shape[1]/2))
    filter += n.where(r2 <= 1, 1, 0)
    return filter.clip(0,1)

twopi = 2 * math.pi

step = twopi/((60/float(opts.binsize))*24.)
bins = n.arange(0,twopi+step,step)
beambins = n.arange((step/2.),twopi+(step/2.),step)
bindict = {}
bin_balun = {}
bin_cable = {}
for index, start in enumerate(bins):
    bindict[index] = []
    bin_balun[index] = []
    bin_cable[index] = []

filegroups = {}
for cnt, filename in enumerate(args):
    basefile = filename.split('__')[0]
    filegroups[basefile] = filegroups.get(basefile, []) + [filename]
srcdata, srctimes, t_balun, t_cable = {}, {}, {}, {}
basefiles = filegroups.keys(); basefiles.sort()
antvis = {}
for basefile in basefiles:
    filenames = filegroups[basefile]; filenames.sort(); filenames.reverse()
    srcs = {}
    for filename in filenames:
        fwords = filename[:-len('.npz')].split('__')
        print filename
        try: f = n.load(filename)
        except:
            print '    Load file failed'
            continue
        if fwords[1] == 'info':
            times = f['times']
            afreqs = f['freqs']
            scores = f['scores']
            cable = f['t_cable']
            balun = f['t_balun']
            SHAPE = times.shape + afreqs.shape
            filter = gen_filter(SHAPE, opts.dw, opts.drw)
            filter_take = n.where(filter)
            def from_coeffs(c):
                d = n.zeros(SHAPE, dtype=n.complex)
                d[filter_take] = c
                return fft2(d) / d.size
        else:
            k = fwords[1]
            srcs[k] = {}
            for i in f.files: srcs[k][int(i)] = f[i]
    best_score = scores.min()
    argclose = n.where(scores < best_score + 2*EXP_NOISE)[0]
    print len(argclose)
    print 'Using Score:', best_score
    srcant = {}
    for k in srcs:
        if not antvis.has_key(k): antvis[k] = {}
        print k
        srcant[k] = {}
        for i in srcs[k]:
            _ant, _wgt = 0, 0
            for iter in argclose:
                w = n.exp((best_score - scores[iter]) / EXP_NOISE)
                _wgt += w
                _ant += srcs[k][i][iter] * w
            srcant[k][i] = from_coeffs(_ant / _wgt)
            if TRIM:
                trim = len(srcant[k][i]) / 4
                srcant[k][i] = srcant[k][i][trim]
            if not antvis[k].has_key(i):
                antvis[k][i] = srcant[k][i]
            else:
                antvis[k][i] = n.append(antvis[k][i],srcant[k][i],axis=0)
                #print antvis[k][i].shape
        if TRIM:
            srctimes[k] = srctimes.get(k,[]) + [times[trim:-trim]]
            t_cable[k] = t_cable.get(k, []) + [cable[trim:-trim]]
            t_balun[k] = t_balun.get(k, []) + [balun[trim:-trim]]
        else:
            srctimes[k] = srctimes.get(k,[]) + [times]
            t_cable[k] = t_cable.get(k, []) + [cable]
            t_balun[k] = t_balun.get(k, []) + [balun]
for k in antvis:
    srctimes[k] = n.concatenate(srctimes[k], axis=0)
    t_cable[k] = n.concatenate(t_cable[k], axis=0)
    t_balun[k] = n.concatenate(t_balun[k], axis=0)
srcs = srcant.keys(); srcs.sort()
if opts.cal != None:
    srclist = []
    for src in srcs:
        radec = src.split('_')
        if len(radec) == 2:
            src = a.phs.RadioFixedBody(ra=radec[0], dec=radec[1], name=src)
        srclist.append(src)
    cat = a.cal.get_catalog(opts.cal, srclist)
    aa = a.cal.get_aa(opts.cal, n.array(opts.freq))
else: cat = {}

if 'cyg' in srcs: srcs = ['cyg'] + srcs
norm=1

#print srctimes['cas'].shape
#print antvis['cas'][0].shape

bm = {}
for k in srcs:
    bm[k] = []
    for bin in beambins:
        time = (bin/twopi)+2455039
        cat.compute(aa)
        aa.set_jultime(time)
        bm[k].append(aa[opts.ant].bm_response(cat[k].get_crds('top'), pol=opts.pol)[0][0])
    
for k in srcs:
    for index, time in enumerate(srctimes[k]):
        aa.set_jultime(time)
        srctimes[k][index] = float(aa.sidereal_time())
    for i in srcant[k]:
        if i != opts.ant: continue
        for cnt, integ in enumerate(antvis[k][i]):
            binlist, binedges = n.histogram(srctimes[k][cnt], bins=bins)
            sample = n.where(binlist == 1)[0][0]
            print sample
            bindict[sample].append((n.median(integ))/(bm[k][sample]*(n.sqrt(cat[k].jys))))
            bin_balun[sample].append(t_balun[k][cnt])
            bin_cable[sample].append(t_cable[k][cnt])

binvar = []
cablevar = []
balunvar = []
for sample in bindict.keys():
    binvar.append(n.var(n.array(bindict[sample])))
    cablevar.append(n.var(n.array(bin_cable[sample])))
    balunvar.append(n.var(n.array(bin_balun[sample])))

#p.plot(bins,binvar,'.')
#p.plot(bins,cablevar,'.')
#p.plot(bins,balunvar,'.')

#p.plot(beambins,bm['cas'],'.')

for sample in bindict.keys():
    p.plot(bin_cable[sample],n.abs(bindict[sample]),'.')
    #p.plot(bin_balun[9],n.abs(bindict[9]),'.')

p.show()

if opts.savez:
    tempdict = {}
    cabledict = {}
    balundict = {}
    for key in bindict.keys():
        tempdict[str(key)] = bindict[key]
        cabledict[str(key)] = bin_cable[key]
        balundict[str(key)] = bin_balun[key]
    del(bindict,bin_cable,bin_balun)

    n.savez('temp_bins.npz',**tempdict)
    n.savez('tc_bins.npz',**cabledict)
    n.savez('tb_bins.npz',**balundict)
