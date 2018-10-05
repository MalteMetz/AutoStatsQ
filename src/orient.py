import numpy as num
import math
from pyrocko import trace, pile
from pyrocko import util
from pyrocko.orthodrome import distance_accurate50m_numpy
from matplotlib import pyplot as plt
from pyrocko.guts import Object, Dict, String, Float, List, Int, Tuple, load
from pyrocko.plot.automap import Map


v_rayleigh = 4.0  # km/s


class dict_stats_rota(Object):
    CorrectAngl_perStat_median = Dict.T(String.T(), Float.T())
    CorrectAngl_perStat_mean = Dict.T(String.T(), Float.T())
    CorrectAngl_perStat_stdd = Dict.T(String.T(), Float.T())


class rota_ev_by_stat(Object):
    station = Tuple.T(2, String.T())
    ev_rota = Dict.T(Float.T(), Int.T())


class dict_stats_all_rota(Object):
    dict_stats_all = List.T(rota_ev_by_stat.T())


class Event_sw(Object):
    station = Tuple.T(2, String.T())
    name = String.T()
    time = String.T()
    max_cc_angle = Int.T()
    max_cc_coef = Float.T()


class Polarity_switch(Object):
    switched_by_stat = List.T(Event_sw.T())


def write_output(list_median_a, list_mean_a, list_stdd_a, list_switched,
                 used_stats, dir_ro):
    if list_switched:
        # write to yaml
        l_sw = [Event_sw(station=(s[0], s[1]), name=s[2],
                         time=s[3], max_cc_angle=s[4], max_cc_coef=s[5])
                for l in list_switched for s in l if s and s[5] > 0.85]

        sw = Polarity_switch(switched_by_stat=l_sw)
        sw.regularize()
        sw.validate()
        sw.dump(filename='%s/Switched_Polarities.yaml'
                % (dir_ro))

    if list_median_a and list_mean_a and list_stdd_a:
        ns_list = ['%s %s' % (st.network, st.station) for st in used_stats]
        perStat_median = dict(zip(map(lambda x: x, ns_list), list_median_a))
        perStat_mean = dict(zip(map(lambda x: x, ns_list), list_mean_a))
        perStat_std = dict(zip(map(lambda x: x, ns_list), list_stdd_a))

        dicts_rota = dict_stats_rota(CorrectAngl_perStat_median=perStat_median,
                                     CorrectAngl_perStat_mean=perStat_mean,
                                     CorrectAngl_perStat_stdd=perStat_std)

        dicts_rota.regularize()
        dicts_rota.validate()
        dicts_rota.dump(filename='%s/CorrectionAngles.yaml'
                        % (dir_ro))


def write_all_output_csv(list_all_angles, used_stats, dir_ro):
    list_rrr = []

    for st, ev_dict in zip(used_stats, list_all_angles):
        rrr = rota_ev_by_stat(station=(st.network, st.station),
                              ev_rota=ev_dict)
        list_rrr.append(rrr)

    dict_save_rot_st_ev = dict_stats_all_rota(dict_stats_all=list_rrr)

    dict_save_rot_st_ev.dump(filename='%s/AllCorrectionAngles.yaml'
                             % (dir_ro))


def get_m_angle_switched(cc_i_ev_vs_rota, catalog, st):
    '''
    1) did polarity swith occur? for single events, say if
    max c-c is closer to 180 deg than to 0 deg! (only trusted if
    coef > 0.85, otherwise might just be noise)
    2) provide median of correction angle associated to max-cc,
    only use those with max cc-coef > 0.85 or sth like that
    '''
    angles = []
    values = []
    switched = []

    for i_ev, ev in enumerate(catalog):
        maxcc_value = num.max(cc_i_ev_vs_rota[i_ev, :])

        if not num.isnan(maxcc_value):
            maxcc_angle = -180 + num.argmax(cc_i_ev_vs_rota[i_ev, :])
            angles.append(maxcc_angle)
            values.append(maxcc_value)

            if abs(0. - maxcc_angle) > 90:
                switched.append((st.network, st.station, ev.name,
                                 util.time_to_str(ev.time),
                                 maxcc_angle, maxcc_value))

    median_a = num.median([a for (a, v) in zip(angles, values) if v > 0.85])
    mean_a = num.mean([a for (a, v) in zip(angles, values) if v > 0.85])
    std_a = num.std([a for (a, v) in zip(angles, values) if v > 0.85])

    return median_a, mean_a, std_a, switched


def get_m_angle_all(cc_i_ev_vs_rota, catalog, st):

    dict_ev_angle = {}

    for i_ev, ev in enumerate(catalog):
        maxcc_value = num.max(cc_i_ev_vs_rota[i_ev, :])

        if not num.isnan(maxcc_value):
            maxcc_angle = -180 + num.argmax(cc_i_ev_vs_rota[i_ev, :])

            if maxcc_angle > 0.85:
                dict_ev_angle[ev.time] = int(maxcc_angle)

    return dict_ev_angle


def get_tr_by_cha(pile, start_twd, end_twd, cha):
    tr = pile.all(
        tmin=start_twd,
        tmax=end_twd,
        trace_selector=lambda tr: tr.nslc_id[3] == cha,
        want_incomplete=False)

    return tr


def max_or_min(c):
    '''
    for testing... not used because valid cc is used which returns only
    one value (no time shifts!)
    Get time and value of maximum of the absolute of data.
    '''
    tmi, mi = c.min()
    tma, ma = c.max()
    if abs(mi) > abs(ma):
        return tmi, mi
    else:
        return tma, ma


def plot_ccdistr_each_event(cc_i_ev_vs_rota, catalog, rot_angles, st, dir_ro):
    '''
    Plots max. cc-coef vs. rotation angle for each event in subplots.
    rather for debugging than for including into normal testing workflow!

    :param cc_i_ev_vs_rota: num.array [i_ev, rot_a] containing max. cc-coef for
                            each rotation angle (rot_a) and event (i_ev)
    :param catalog: list of pyrocko events used for analysis
    :param rot_angles: range of rotation angles
    :param st: current station (pyrocko Station)
    :param dir_ro: output directory
    '''
    n_ev = len(catalog)
    nrows = math.ceil(n_ev / 5)
    ncols = 5
    y_lim = (-1., 1.)
    x_lim = (-180, 180)
    fig, ax = plt.subplots(nrows=nrows, ncols=ncols, figsize=(15, 9))
    for (i_row, row), ev in zip(enumerate(cc_i_ev_vs_rota), catalog):
        i_x = int(i_row/ncols)
        i_y = int(i_row % ncols)
        ev_time_str = util.time_to_str(ev.time)[0:10]
        ax[i_x, i_y].set_title(ev_time_str)
        if i_x == nrows-1:
            ax[i_x, i_y].set_xlabel('Correction angle [deg]')
        if i_y == 0:
            ax[i_x, i_y].set_ylabel('C-c coef.')
        ax[i_x, i_y].plot(rot_angles, row, 'k')
        ax[i_x, i_y].set_xlim(x_lim)
        ax[i_x, i_y].set_ylim(y_lim)
        ax[i_x, i_y].set_xticks([-180, 0, 180])

    if nrows*ncols > n_ev:
        dif = nrows*ncols - n_ev
        for i in range(dif):
            ax[i_x, i_y+i+1].set_xlabel('Correction angle [deg]')
    plt.tight_layout()
    # plt.show()
    fig.savefig('%s/%s_%s_distr.pdf'
                % (dir_ro, st.network, st.station))
    plt.close(fig)


def prep_orient(datapath, st, catalog, dir_ro,
                bp, dt_start, dt_stop,
                plot_heatmap=False,  plot_distr=False):
    '''
    Perform orientation analysis using Rayleigh waves, main function.

    time wdw: 20s before 4.0km/s arrival and 600 s afterwards
    (Stachnik et al. 2012)
    - compute radial component for back values of 0 to 360 deg
    - for each c-c of hilbert(R) with Z comp.
    - call plotting functions and/or write results to file

    :param datapath: path to rrd data
    :param st: current station (pyrocko station object)
    :param catalog: list of pyrocko events used for analysis
    :param dir_ro: output directory
    :param plot_heatmap: bool, optional
    :param plot_distr: bool, optional
    '''

    st_data_pile = pile.make_pile(datapath, regex='_%s_' % st.station,
                                  show_progress=False)
    n_ev = len(catalog)
    if st_data_pile.tmin is not None and st_data_pile.tmax is not None:

        # calculate dist between all events and current station
        r_arr_by_ev = num.empty(n_ev)
        ev_lats = num.asarray([ev.lat for ev in catalog])
        ev_lons = num.asarray([ev.lon for ev in catalog])
        dists = distance_accurate50m_numpy(a_lats=ev_lats, a_lons=ev_lons,
                                           b_lats=st.lat, b_lons=st.lon,
                                           implementation='c')
        r_arr_by_ev = (dists/1000.) / v_rayleigh
        cc_i_ev_vs_rota = num.empty((n_ev, 360))
        rot_angles = range(-180, 180, 1)
        print(st.network, st.station)
        for i_ev, ev in enumerate(catalog):
            arrT = ev.time + r_arr_by_ev[i_ev]

            start_twd1 = ev.time
            end_twd1 = arrT + 1800
            # if st.station == 'MATE':
            #     print('origin time:', util.time_to_str(ev.time))
            #     print('start:', util.time_to_str(start_twd),'end:',
            #           util.time_to_str(end_twd) )
            #     print('arrT:', util.time_to_str(arrT))

            trZ = get_tr_by_cha(st_data_pile, start_twd1, end_twd1, 'Z')
            trR = get_tr_by_cha(st_data_pile, start_twd1, end_twd1, 'R')
            trT = get_tr_by_cha(st_data_pile, start_twd1, end_twd1, 'T')

            start_twd2 = ev.time + r_arr_by_ev[i_ev] - dt_start
            end_twd2 = arrT + dt_stop

            # if st.station == 'MATE':
            #    trace.snuffle([trZ[0],trR[0],trT[0]])

            # print(len(trZ), len(trR), len(trT))
            # print(trZ)
            if len(trZ) == 1 and len(trR) == 1 and len(trT) == 1:
                trZ = trZ[0]
                trR = trR[0]
                trT = trT[0]

            else:
                cc_i_ev_vs_rota[i_ev, :] = num.nan
                continue
            trZ.bandpass(bp[0], bp[1], bp[2])
            trZ.chop(tmin=start_twd2, tmax=end_twd2)

            for i_r, r in enumerate(rot_angles):
                # print('rotation angle %s deg' % r)
                rot_2, rot_3 = trace.rotate(traces=[trR, trT], azimuth=r,
                                            in_channels=['R', 'T'],
                                            out_channels=['2', '3'])
                rot_2_y = rot_2.ydata
                rot_2_hilb = num.imag(trace.hilbert(rot_2_y, len(rot_2_y)))
                rot_2_hilb_tr = trace.Trace(deltat=rot_2.deltat,
                                            ydata=rot_2_hilb,
                                            tmin=rot_2.tmin)
                # problem: rot_2 and rot_2_hilb look exactly the same!
                # --> no phase shift. why? should be num.imag!!!
                # trace.snuffle([rot_2, rot_2_hilb_tr])
                rot_2_hilb_tr.bandpass(bp[0], bp[1], bp[2])
                rot_2_hilb_tr.chop(tmin=start_twd2, tmax=end_twd2)

                # if st.station == 'RORO' and r == 0:
                #     trace.snuffle([rot_2_hilb_tr, trZ])
                # normalize traces
                trZ.ydata /= abs(max(trZ.ydata))
                rot_2_hilb_tr.ydata /= abs(max(rot_2_hilb_tr.ydata))

                c = trace.correlate(trZ, rot_2_hilb_tr,
                                    mode='valid',
                                    normalization='normal')

                t, coef = c.max()
                t2, coef2 = max_or_min(c)
                '''
                if st.station == 'MATE' and r == 0:
                    print(i_ev, ev.name, ev.depth)
                    print(r, t, coef, t2, coef2)
                    trace.snuffle([trZ, trR, rot_2_hilb_tr])
                '''
                cc_i_ev_vs_rota[i_ev, i_r] = coef
        '''
        if st.station == 'MATE':
            for i_ev in range(n_ev):
                print(num.argmax(cc_i_ev_vs_rota[i_ev,:]),
                      num.max(cc_i_ev_vs_rota[i_ev,:]))
        '''

        if plot_heatmap is True:
            fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(8, 2))

            cax = ax.imshow(cc_i_ev_vs_rota, interpolation='nearest',
                            vmin=-1.0, vmax=1.0,
                            aspect='auto', extent=[-180, 180, n_ev, 0],
                            cmap='binary')
            ax.set_ylabel('i_ev')
            ax.set_xlabel('Correction angle (deg)')
            ax.set_title('%s %s' % (st.network, st.station))
            cbar = fig.colorbar(cax, ticks=[0, 0.5, 1.0],
                                orientation='horizontal',
                                fraction=0.05, pad=0.5)
            cbar.ax.set_xticklabels(['0', '0.5', '1.0'])
            plt.tight_layout()
            # plt.show(fig)
            fig.savefig('%s/%s_%s_rot_cc_heatmap.png'
                        % (dir_ro, st.network, st.station))
            plt.close()

        if plot_distr is True:
            plot_ccdistr_each_event(cc_i_ev_vs_rota, catalog,
                                    rot_angles, st, dir_ro)

        median_a, mean_a, std_a, switched =\
            get_m_angle_switched(cc_i_ev_vs_rota, catalog, st)

        dict_ev_angle = get_m_angle_all(cc_i_ev_vs_rota, catalog, st)

        return median_a, mean_a, std_a, switched, dict_ev_angle


def plot_corr_angles(ns, st_lats, st_lons, orientfile, dir_orient,
                     pl_options, mapsize, ls=False):
    '''
    Plot correction angles of all stations on a map. nans are igored.
    Values for plotting are read from file which was automatically prepared in
    the orient section.

    :param ls: label position [lon (symbol), lat (symbol + label), lon (label)]
    '''

    gmtconf = dict(
                   MAP_TICK_PEN_PRIMARY='1.25p',
                   MAP_TICK_PEN_SECONDARY='1.25p',
                   MAP_TICK_LENGTH_PRIMARY='0.2c',
                   MAP_TICK_LENGTH_SECONDARY='0.6c',
                   FONT_ANNOT_PRIMARY='20p,1,black',
                   FONT_LABEL='20p,1,black',
                   PS_CHAR_ENCODING='ISOLatin1+',
                   MAP_FRAME_TYPE='fancy',
                   FORMAT_GEO_MAP='D',
                   PS_PAGE_ORIENTATION='portrait',
                   MAP_GRID_PEN_PRIMARY='thinnest,0/50/0',
                   MAP_ANNOT_OBLIQUE='6')

    angles_fromfile = load(filename=dir_orient+orientfile)

    angle_no_nan = []
    lat_no_nan = []
    lon_no_nan = []

    for i_ns, ns_now in enumerate(ns):
        for l in ['00', '', '01']:
            try:
                ns_now = '%s %s' % (ns_now[0], ns_now[1])
                a = angles_fromfile.CorrectAngl_perStat_median[ns_now]
                if a > -181.0 and a < 180.0:  # not nan
                    angle_no_nan.append(a)
                    # stats_no_nan.append(ns_now[1])
                    lat_no_nan.append(st_lats[i_ns])
                    lon_no_nan.append(st_lons[i_ns])
            except KeyError:
                continue

    # Generate the basic map
    m = Map(
        lat=pl_options[0],
        lon=pl_options[1],
        radius=pl_options[2],
        width=mapsize[0],
        height=mapsize[1],
        show_grid=False,
        show_topo=True,
        illuminate=True,
        illuminate_factor_ocean=0.15,
        show_rivers=True,
        show_plates=False,
        gmt_config=gmtconf)

    # Draw some larger cities covered by the map area
    # m.draw_cities()

    # same length for every vector:
    length = [0.9 for a in range(len(lat_no_nan))]

    # plot obtained rotation vectors:
    m.gmt.psxy(in_columns=(lon_no_nan, lat_no_nan, angle_no_nan, length),
               S='V0.5c+jc', W='0.07c,red',
               *m.jxyr)

    # add handmade label
    if label_settings:
        m.gmt.psxy(in_columns=([ls[0]], [ls[1]], [ls[1]], [0.9]),
                   S='V0.5c', W='0.07c,red', *m.jxyr)
        labels = ['Correction angle']
        lat_lab = [ls[1]]
        lon_lab = [ls[2]]
        for i in range(len(labels)):
            m.add_label(lat_lab[i], lon_lab[i], labels[i])

    m.save(dir_orient+'map_orient.png')
    print('Saved map with corr. angles for sensor orientations')