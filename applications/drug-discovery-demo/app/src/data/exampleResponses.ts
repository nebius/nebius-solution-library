/**
 * Example API responses for the NIM Playground structure prediction NIMs.
 * Generated from actual API calls to OpenFold3, Boltz2, and OpenFold2
 * using villin headpiece HP35 (PDB: 1YRF, 35 residues): LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
 */

import type { PlaygroundResult } from './nimPlayground';

// ============================================================================
// OpenFold3 Example
// ============================================================================

export const OPENFOLD3_STRUCTURE = `ATOM      1  N   LEU A   1      16.335   0.152  -7.304  1.00 49.43           N  
ATOM      2  CA  LEU A   1      15.922  -0.082  -5.917  1.00 48.88           C  
ATOM      3  C   LEU A   1      16.009  -1.565  -5.602  1.00 49.63           C  
ATOM      4  O   LEU A   1      15.781  -2.404  -6.461  1.00 47.77           O  
ATOM      5  CB  LEU A   1      14.477   0.378  -5.730  1.00 48.24           C  
ATOM      6  CG  LEU A   1      14.326   1.889  -5.764  1.00 45.55           C  
ATOM      7  CD1 LEU A   1      12.862   2.256  -5.842  1.00 43.32           C  
ATOM      8  CD2 LEU A   1      14.962   2.525  -4.552  1.00 42.54           C  
ATOM      9  N   SER A   2      16.380  -1.845  -4.411  1.00 48.67           N  
ATOM     10  CA  SER A   2      16.493  -3.230  -3.989  1.00 48.00           C  
ATOM     11  C   SER A   2      15.239  -3.637  -3.223  1.00 49.13           C  
ATOM     12  O   SER A   2      14.448  -2.795  -2.828  1.00 47.16           O  
ATOM     13  CB  SER A   2      17.720  -3.387  -3.089  1.00 46.88           C  
ATOM     14  OG  SER A   2      18.327  -4.621  -3.327  1.00 43.31           O  
ATOM     15  N   ASP A   3      15.100  -4.914  -3.026  1.00 48.33           N  
ATOM     16  CA  ASP A   3      13.927  -5.400  -2.306  1.00 47.15           C  
ATOM     17  C   ASP A   3      13.840  -4.784  -0.918  1.00 47.93           C  
ATOM     18  O   ASP A   3      12.778  -4.449  -0.436  1.00 46.79           O  
ATOM     19  CB  ASP A   3      14.025  -6.919  -2.185  1.00 46.46           C  
ATOM     20  CG  ASP A   3      13.485  -7.575  -3.430  1.00 43.89           C  
ATOM     21  OD1 ASP A   3      12.396  -7.205  -3.877  1.00 41.41           O  
ATOM     22  OD2 ASP A   3      14.149  -8.463  -3.971  1.00 42.26           O  
ATOM     23  N   GLU A   4      14.964  -4.654  -0.302  1.00 51.24           N  
ATOM     24  CA  GLU A   4      14.987  -4.061   1.032  1.00 50.98           C  
ATOM     25  C   GLU A   4      14.479  -2.629   0.992  1.00 51.86           C  
ATOM     26  O   GLU A   4      13.759  -2.188   1.871  1.00 50.73           O  
ATOM     27  CB  GLU A   4      16.401  -4.081   1.580  1.00 50.28           C  
ATOM     28  CG  GLU A   4      16.831  -5.481   1.941  1.00 47.00           C  
ATOM     29  CD  GLU A   4      17.909  -5.443   3.005  1.00 44.58           C  
ATOM     30  OE1 GLU A   4      18.724  -4.538   2.950  1.00 41.55           O  
ATOM     31  OE2 GLU A   4      17.907  -6.297   3.883  1.00 40.68           O  
ATOM     32  N   ASP A   5      14.845  -1.923  -0.037  1.00 52.20           N  
ATOM     33  CA  ASP A   5      14.401  -0.541  -0.177  1.00 51.54           C  
ATOM     34  C   ASP A   5      12.882  -0.487  -0.290  1.00 52.24           C  
ATOM     35  O   ASP A   5      12.220   0.358   0.290  1.00 51.42           O  
ATOM     36  CB  ASP A   5      15.040   0.081  -1.413  1.00 51.07           C  
ATOM     37  CG  ASP A   5      15.958   1.223  -1.046  1.00 48.36           C  
ATOM     38  OD1 ASP A   5      15.610   1.989  -0.152  1.00 44.93           O  
ATOM     39  OD2 ASP A   5      17.028   1.335  -1.663  1.00 45.56           O  
ATOM     40  N   PHE A   6      12.372  -1.406  -1.034  1.00 51.18           N  
ATOM     41  CA  PHE A   6      10.920  -1.465  -1.203  1.00 51.12           C  
ATOM     42  C   PHE A   6      10.232  -1.650   0.138  1.00 51.36           C  
ATOM     43  O   PHE A   6       9.219  -1.033   0.427  1.00 51.72           O  
ATOM     44  CB  PHE A   6      10.567  -2.624  -2.118  1.00 51.79           C  
ATOM     45  CG  PHE A   6      10.433  -2.150  -3.537  1.00 50.56           C  
ATOM     46  CD1 PHE A   6      11.536  -2.116  -4.372  1.00 48.11           C  
ATOM     47  CD2 PHE A   6       9.202  -1.767  -4.040  1.00 47.34           C  
ATOM     48  CE1 PHE A   6      11.419  -1.687  -5.672  1.00 46.22           C  
ATOM     49  CE2 PHE A   6       9.073  -1.327  -5.353  1.00 46.09           C  
ATOM     50  CZ  PHE A   6      10.184  -1.291  -6.168  1.00 46.87           C  
ATOM     51  N   LYS A   7      10.783  -2.493   0.921  1.00 53.97           N  
ATOM     52  CA  LYS A   7      10.211  -2.749   2.241  1.00 53.41           C  
ATOM     53  C   LYS A   7      10.210  -1.488   3.083  1.00 54.29           C  
ATOM     54  O   LYS A   7       9.243  -1.167   3.741  1.00 54.08           O  
ATOM     55  CB  LYS A   7      11.008  -3.840   2.950  1.00 53.32           C  
ATOM     56  CG  LYS A   7      10.483  -5.205   2.580  1.00 52.23           C  
ATOM     57  CD  LYS A   7      11.152  -6.256   3.431  1.00 51.58           C  
ATOM     58  CE  LYS A   7      10.231  -7.443   3.629  1.00 49.34           C  
ATOM     59  NZ  LYS A   7      10.864  -8.480   4.418  1.00 46.63           N1+
ATOM     60  N   ALA A   8      11.305  -0.784   3.020  1.00 52.24           N  
ATOM     61  CA  ALA A   8      11.413   0.438   3.804  1.00 52.14           C  
ATOM     62  C   ALA A   8      10.384   1.461   3.349  1.00 53.36           C  
ATOM     63  O   ALA A   8       9.683   2.068   4.154  1.00 53.48           O  
ATOM     64  CB  ALA A   8      12.811   0.999   3.673  1.00 52.21           C  
ATOM     65  N   VAL A   9      10.299   1.628   2.055  1.00 50.36           N  
ATOM     66  CA  VAL A   9       9.337   2.584   1.509  1.00 49.34           C  
ATOM     67  C   VAL A   9       7.917   2.138   1.808  1.00 50.15           C  
ATOM     68  O   VAL A   9       7.068   2.924   2.203  1.00 49.37           O  
ATOM     69  CB  VAL A   9       9.533   2.706  -0.000  1.00 49.34           C  
ATOM     70  CG1 VAL A   9      10.924   3.222  -0.302  1.00 45.99           C  
ATOM     71  CG2 VAL A   9       8.498   3.638  -0.587  1.00 46.49           C  
ATOM     72  N   PHE A  10       7.671   0.889   1.615  1.00 52.72           N  
ATOM     73  CA  PHE A  10       6.336   0.358   1.869  1.00 52.10           C  
ATOM     74  C   PHE A  10       5.951   0.542   3.328  1.00 52.67           C  
ATOM     75  O   PHE A  10       4.832   0.909   3.641  1.00 51.30           O  
ATOM     76  CB  PHE A  10       6.321  -1.112   1.510  1.00 52.01           C  
ATOM     77  CG  PHE A  10       4.927  -1.666   1.574  1.00 50.85           C  
ATOM     78  CD1 PHE A  10       4.501  -2.355   2.698  1.00 48.66           C  
ATOM     79  CD2 PHE A  10       4.046  -1.494   0.521  1.00 48.45           C  
ATOM     80  CE1 PHE A  10       3.210  -2.855   2.766  1.00 47.27           C  
ATOM     81  CE2 PHE A  10       2.754  -1.986   0.576  1.00 45.81           C  
ATOM     82  CZ  PHE A  10       2.339  -2.672   1.699  1.00 46.33           C  
ATOM     83  N   GLY A  11       6.896   0.279   4.196  1.00 50.79           N  
ATOM     84  CA  GLY A  11       6.616   0.436   5.615  1.00 49.35           C  
ATOM     85  C   GLY A  11       6.289   1.868   5.957  1.00 50.74           C  
ATOM     86  O   GLY A  11       5.345   2.153   6.693  1.00 49.01           O  
ATOM     87  N   MET A  12       7.062   2.766   5.401  1.00 54.78           N  
ATOM     88  CA  MET A  12       6.829   4.178   5.653  1.00 53.71           C  
ATOM     89  C   MET A  12       5.471   4.601   5.120  1.00 54.90           C  
ATOM     90  O   MET A  12       4.710   5.290   5.775  1.00 53.30           O  
ATOM     91  CB  MET A  12       7.927   5.001   4.996  1.00 53.22           C  
ATOM     92  CG  MET A  12       7.899   6.420   5.489  1.00 51.50           C  
ATOM     93  SD  MET A  12       9.226   7.368   4.776  1.00 50.18           S  
ATOM     94  CE  MET A  12       9.011   8.917   5.645  1.00 47.07           C  
ATOM     95  N   THR A  13       5.197   4.186   3.922  1.00 51.56           N  
ATOM     96  CA  THR A  13       3.916   4.534   3.311  1.00 50.95           C  
ATOM     97  C   THR A  13       2.764   3.909   4.080  1.00 51.99           C  
ATOM     98  O   THR A  13       1.720   4.517   4.262  1.00 50.98           O  
ATOM     99  CB  THR A  13       3.890   4.043   1.869  1.00 50.19           C  
ATOM    100  OG1 THR A  13       5.000   4.578   1.171  1.00 46.90           O  
ATOM    101  CG2 THR A  13       2.612   4.501   1.179  1.00 46.12           C  
ATOM    102  N   ARG A  14       2.966   2.700   4.488  1.00 53.39           N  
ATOM    103  CA  ARG A  14       1.911   2.012   5.227  1.00 52.22           C  
ATOM    104  C   ARG A  14       1.591   2.742   6.518  1.00 53.29           C  
ATOM    105  O   ARG A  14       0.438   2.776   6.940  1.00 50.52           O  
ATOM    106  CB  ARG A  14       2.372   0.590   5.537  1.00 50.35           C  
ATOM    107  CG  ARG A  14       1.196  -0.240   5.980  1.00 45.96           C  
ATOM    108  CD  ARG A  14       1.501  -1.717   5.839  1.00 43.64           C  
ATOM    109  NE  ARG A  14       2.263  -2.197   6.993  1.00 40.83           N  
ATOM    110  CZ  ARG A  14       2.659  -3.417   7.125  1.00 38.27           C  
ATOM    111  NH1 ARG A  14       2.369  -4.313   6.209  1.00 37.97           N  
ATOM    112  NH2 ARG A  14       3.345  -3.763   8.166  1.00 36.15           N1+
ATOM    113  N   SER A  15       2.606   3.298   7.114  1.00 56.12           N  
ATOM    114  CA  SER A  15       2.402   4.018   8.369  1.00 55.14           C  
ATOM    115  C   SER A  15       1.386   5.139   8.158  1.00 56.18           C  
ATOM    116  O   SER A  15       0.472   5.332   8.949  1.00 54.50           O  
ATOM    117  CB  SER A  15       3.722   4.588   8.853  1.00 54.05           C  
ATOM    118  OG  SER A  15       3.544   5.177  10.112  1.00 49.37           O  
ATOM    119  N   ALA A  16       1.569   5.866   7.101  1.00 53.25           N  
ATOM    120  CA  ALA A  16       0.647   6.968   6.805  1.00 52.60           C  
ATOM    121  C   ALA A  16      -0.690   6.421   6.334  1.00 53.47           C  
ATOM    122  O   ALA A  16      -1.740   7.002   6.585  1.00 52.25           O  
ATOM    123  CB  ALA A  16       1.253   7.852   5.738  1.00 51.62           C  
ATOM    124  N   PHE A  17      -0.621   5.306   5.667  1.00 55.66           N  
ATOM    125  CA  PHE A  17      -1.855   4.696   5.165  1.00 55.29           C  
ATOM    126  C   PHE A  17      -2.727   4.217   6.315  1.00 55.67           C  
ATOM    127  O   PHE A  17      -3.949   4.331   6.277  1.00 54.94           O  
ATOM    128  CB  PHE A  17      -1.479   3.522   4.278  1.00 55.06           C  
ATOM    129  CG  PHE A  17      -2.639   3.049   3.467  1.00 53.58           C  
ATOM    130  CD1 PHE A  17      -2.945   3.661   2.261  1.00 51.03           C  
ATOM    131  CD2 PHE A  17      -3.420   1.979   3.886  1.00 50.12           C  
ATOM    132  CE1 PHE A  17      -4.014   3.217   1.503  1.00 48.37           C  
ATOM    133  CE2 PHE A  17      -4.491   1.533   3.138  1.00 47.54           C  
ATOM    134  CZ  PHE A  17      -4.782   2.155   1.940  1.00 47.85           C  
ATOM    135  N   ALA A  18      -2.092   3.675   7.289  1.00 53.43           N  
ATOM    136  CA  ALA A  18      -2.833   3.180   8.437  1.00 52.61           C  
ATOM    137  C   ALA A  18      -3.509   4.315   9.194  1.00 53.60           C  
ATOM    138  O   ALA A  18      -4.468   4.099   9.922  1.00 52.31           O  
ATOM    139  CB  ALA A  18      -1.885   2.434   9.359  1.00 51.77           C  
ATOM    140  N   ASN A  19      -2.986   5.481   9.001  1.00 56.95           N  
ATOM    141  CA  ASN A  19      -3.562   6.635   9.671  1.00 56.35           C  
ATOM    142  C   ASN A  19      -4.916   6.991   9.071  1.00 57.14           C  
ATOM    143  O   ASN A  19      -5.716   7.698   9.664  1.00 56.78           O  
ATOM    144  CB  ASN A  19      -2.618   7.822   9.531  1.00 56.00           C  
ATOM    145  CG  ASN A  19      -3.008   8.932  10.471  1.00 53.26           C  
ATOM    146  OD1 ASN A  19      -3.439   8.697  11.583  1.00 50.07           O  
ATOM    147  ND2 ASN A  19      -2.862  10.166  10.041  1.00 49.53           N  
ATOM    148  N   LEU A  20      -5.160   6.527   7.908  1.00 57.12           N  
ATOM    149  CA  LEU A  20      -6.418   6.810   7.236  1.00 56.65           C  
ATOM    150  C   LEU A  20      -7.532   5.927   7.786  1.00 57.65           C  
ATOM    151  O   LEU A  20      -7.274   4.867   8.343  1.00 56.13           O  
ATOM    152  CB  LEU A  20      -6.262   6.546   5.743  1.00 55.41           C  
ATOM    153  CG  LEU A  20      -5.248   7.448   5.070  1.00 53.04           C  
ATOM    154  CD1 LEU A  20      -4.970   6.955   3.656  1.00 49.92           C  
ATOM    155  CD2 LEU A  20      -5.729   8.878   5.040  1.00 49.78           C  
ATOM    156  N   PRO A  21      -8.750   6.338   7.620  1.00 57.73           N  
ATOM    157  CA  PRO A  21      -9.889   5.563   8.085  1.00 56.77           C  
ATOM    158  C   PRO A  21      -9.987   4.241   7.340  1.00 57.68           C  
ATOM    159  O   PRO A  21      -9.494   4.086   6.229  1.00 56.46           O  
ATOM    160  CB  PRO A  21     -11.078   6.463   7.767  1.00 55.77           C  
ATOM    161  CG  PRO A  21     -10.586   7.408   6.735  1.00 54.62           C  
ATOM    162  CD  PRO A  21      -9.128   7.587   6.980  1.00 55.33           C  
ATOM    163  N   LEU A  22     -10.656   3.307   7.962  1.00 57.41           N  
ATOM    164  CA  LEU A  22     -10.766   1.980   7.377  1.00 56.64           C  
ATOM    165  C   LEU A  22     -11.439   2.026   6.015  1.00 57.46           C  
ATOM    166  O   LEU A  22     -11.002   1.382   5.069  1.00 55.89           O  
ATOM    167  CB  LEU A  22     -11.565   1.091   8.323  1.00 55.63           C  
ATOM    168  CG  LEU A  22     -11.521  -0.375   7.935  1.00 52.66           C  
ATOM    169  CD1 LEU A  22     -12.468  -1.181   8.825  1.00 49.77           C  
ATOM    170  CD2 LEU A  22     -10.121  -0.926   8.068  1.00 48.82           C  
ATOM    171  N   TRP A  23     -12.470   2.792   5.909  1.00 52.41           N  
ATOM    172  CA  TRP A  23     -13.192   2.856   4.637  1.00 51.11           C  
ATOM    173  C   TRP A  23     -12.292   3.393   3.525  1.00 52.66           C  
ATOM    174  O   TRP A  23     -12.346   2.939   2.391  1.00 51.29           O  
ATOM    175  CB  TRP A  23     -14.403   3.748   4.809  1.00 50.13           C  
ATOM    176  CG  TRP A  23     -14.060   5.143   5.220  1.00 47.91           C  
ATOM    177  CD1 TRP A  23     -14.054   5.646   6.482  1.00 45.01           C  
ATOM    178  CD2 TRP A  23     -13.700   6.245   4.349  1.00 46.78           C  
ATOM    179  NE1 TRP A  23     -13.717   6.968   6.462  1.00 43.21           N  
ATOM    180  CE2 TRP A  23     -13.481   7.366   5.157  1.00 43.61           C  
ATOM    181  CE3 TRP A  23     -13.541   6.366   2.966  1.00 40.81           C  
ATOM    182  CZ2 TRP A  23     -13.120   8.615   4.630  1.00 40.33           C  
ATOM    183  CZ3 TRP A  23     -13.168   7.603   2.436  1.00 39.28           C  
ATOM    184  CH2 TRP A  23     -12.975   8.711   3.271  1.00 39.23           C  
ATOM    185  N   LYS A  24     -11.473   4.335   3.876  1.00 51.38           N  
ATOM    186  CA  LYS A  24     -10.549   4.902   2.881  1.00 50.23           C  
ATOM    187  C   LYS A  24      -9.486   3.881   2.499  1.00 51.23           C  
ATOM    188  O   LYS A  24      -9.111   3.759   1.336  1.00 50.50           O  
ATOM    189  CB  LYS A  24      -9.899   6.155   3.452  1.00 49.83           C  
ATOM    190  CG  LYS A  24      -9.285   6.983   2.346  1.00 48.56           C  
ATOM    191  CD  LYS A  24      -8.887   8.334   2.888  1.00 47.82           C  
ATOM    192  CE  LYS A  24      -8.076   9.103   1.851  1.00 44.99           C  
ATOM    193  NZ  LYS A  24      -8.966   9.677   0.833  1.00 43.30           N1+
ATOM    194  N   GLN A  25      -8.997   3.190   3.455  1.00 53.50           N  
ATOM    195  CA  GLN A  25      -7.982   2.175   3.185  1.00 52.59           C  
ATOM    196  C   GLN A  25      -8.530   1.103   2.254  1.00 53.26           C  
ATOM    197  O   GLN A  25      -7.880   0.687   1.295  1.00 52.78           O  
ATOM    198  CB  GLN A  25      -7.564   1.538   4.500  1.00 52.45           C  
ATOM    199  CG  GLN A  25      -6.781   2.493   5.372  1.00 51.09           C  
ATOM    200  CD  GLN A  25      -6.401   1.845   6.677  1.00 50.18           C  
ATOM    201  OE1 GLN A  25      -6.342   0.630   6.778  1.00 47.61           O  
ATOM    202  NE2 GLN A  25      -6.145   2.637   7.688  1.00 47.83           N  
ATOM    203  N   GLN A  26      -9.709   0.681   2.558  1.00 54.83           N  
ATOM    204  CA  GLN A  26     -10.312  -0.349   1.719  1.00 53.95           C  
ATOM    205  C   GLN A  26     -10.553   0.150   0.298  1.00 54.82           C  
ATOM    206  O   GLN A  26     -10.372  -0.571  -0.669  1.00 53.25           O  
ATOM    207  CB  GLN A  26     -11.644  -0.760   2.354  1.00 53.08           C  
ATOM    208  CG  GLN A  26     -11.431  -1.554   3.628  1.00 49.68           C  
ATOM    209  CD  GLN A  26     -12.079  -2.910   3.514  1.00 47.35           C  
ATOM    210  OE1 GLN A  26     -11.812  -3.653   2.587  1.00 43.73           O  
ATOM    211  NE2 GLN A  26     -12.956  -3.226   4.430  1.00 42.55           N  
ATOM    212  N   ASN A  27     -10.951   1.366   0.213  1.00 55.16           N  
ATOM    213  CA  ASN A  27     -11.205   1.939  -1.105  1.00 54.59           C  
ATOM    214  C   ASN A  27      -9.929   1.998  -1.936  1.00 55.13           C  
ATOM    215  O   ASN A  27      -9.912   1.609  -3.099  1.00 54.73           O  
ATOM    216  CB  ASN A  27     -11.782   3.336  -0.934  1.00 54.39           C  
ATOM    217  CG  ASN A  27     -13.128   3.443  -1.611  1.00 52.18           C  
ATOM    218  OD1 ASN A  27     -13.304   2.993  -2.717  1.00 49.11           O  
ATOM    219  ND2 ASN A  27     -14.086   4.036  -0.932  1.00 49.14           N  
ATOM    220  N   LEU A  28      -8.886   2.474  -1.341  1.00 50.95           N  
ATOM    221  CA  LEU A  28      -7.610   2.572  -2.053  1.00 50.03           C  
ATOM    222  C   LEU A  28      -7.099   1.183  -2.423  1.00 51.14           C  
ATOM    223  O   LEU A  28      -6.626   0.950  -3.536  1.00 50.38           O  
ATOM    224  CB  LEU A  28      -6.594   3.289  -1.168  1.00 49.62           C  
ATOM    225  CG  LEU A  28      -6.899   4.774  -1.004  1.00 47.85           C  
ATOM    226  CD1 LEU A  28      -5.979   5.390   0.031  1.00 46.18           C  
ATOM    227  CD2 LEU A  28      -6.735   5.504  -2.319  1.00 46.27           C  
ATOM    228  N   LYS A  29      -7.190   0.286  -1.511  1.00 50.05           N  
ATOM    229  CA  LYS A  29      -6.725  -1.081  -1.772  1.00 49.76           C  
ATOM    230  C   LYS A  29      -7.535  -1.719  -2.894  1.00 50.80           C  
ATOM    231  O   LYS A  29      -7.005  -2.401  -3.758  1.00 50.35           O  
ATOM    232  CB  LYS A  29      -6.860  -1.913  -0.503  1.00 49.67           C  
ATOM    233  CG  LYS A  29      -5.768  -1.593   0.484  1.00 48.11           C  
ATOM    234  CD  LYS A  29      -5.978  -2.421   1.745  1.00 47.43           C  
ATOM    235  CE  LYS A  29      -4.891  -2.124   2.748  1.00 45.08           C  
ATOM    236  NZ  LYS A  29      -5.069  -2.951   3.968  1.00 42.33           N1+
ATOM    237  N   LYS A  30      -8.797  -1.489  -2.839  1.00 50.78           N  
ATOM    238  CA  LYS A  30      -9.670  -2.075  -3.858  1.00 49.86           C  
ATOM    239  C   LYS A  30      -9.417  -1.436  -5.214  1.00 50.68           C  
ATOM    240  O   LYS A  30      -9.390  -2.108  -6.234  1.00 49.46           O  
ATOM    241  CB  LYS A  30     -11.121  -1.873  -3.433  1.00 49.10           C  
ATOM    242  CG  LYS A  30     -12.060  -2.667  -4.317  1.00 46.20           C  
ATOM    243  CD  LYS A  30     -13.484  -2.554  -3.819  1.00 44.99           C  
ATOM    244  CE  LYS A  30     -14.418  -3.320  -4.726  1.00 41.64           C  
ATOM    245  NZ  LYS A  30     -15.787  -3.365  -4.170  1.00 39.09           N1+
ATOM    246  N   GLU A  31      -9.240  -0.167  -5.207  1.00 51.43           N  
ATOM    247  CA  GLU A  31      -9.018   0.560  -6.459  1.00 50.74           C  
ATOM    248  C   GLU A  31      -7.698   0.129  -7.099  1.00 51.57           C  
ATOM    249  O   GLU A  31      -7.601  -0.030  -8.303  1.00 49.87           O  
ATOM    250  CB  GLU A  31      -8.999   2.047  -6.170  1.00 50.09           C  
ATOM    251  CG  GLU A  31      -9.083   2.832  -7.456  1.00 47.21           C  
ATOM    252  CD  GLU A  31      -9.273   4.309  -7.169  1.00 45.43           C  
ATOM    253  OE1 GLU A  31      -9.425   4.656  -5.998  1.00 43.54           O  
ATOM    254  OE2 GLU A  31      -9.277   5.091  -8.117  1.00 43.25           O  
ATOM    255  N   LYS A  32      -6.721  -0.049  -6.278  1.00 46.85           N  
ATOM    256  CA  LYS A  32      -5.415  -0.445  -6.801  1.00 45.42           C  
ATOM    257  C   LYS A  32      -5.388  -1.949  -7.085  1.00 46.62           C  
ATOM    258  O   LYS A  32      -4.705  -2.408  -7.995  1.00 44.53           O  
ATOM    259  CB  LYS A  32      -4.332  -0.084  -5.772  1.00 44.21           C  
ATOM    260  CG  LYS A  32      -3.096   0.446  -6.457  1.00 42.23           C  
ATOM    261  CD  LYS A  32      -3.417   1.714  -7.195  1.00 40.98           C  
ATOM    262  CE  LYS A  32      -2.170   2.382  -7.736  1.00 38.68           C  
ATOM    263  NZ  LYS A  32      -2.548   3.589  -8.504  1.00 37.17           N1+
ATOM    264  N   GLY A  33      -6.090  -2.677  -6.313  1.00 41.54           N  
ATOM    265  CA  GLY A  33      -6.139  -4.126  -6.514  1.00 40.17           C  
ATOM    266  C   GLY A  33      -4.798  -4.785  -6.239  1.00 41.72           C  
ATOM    267  O   GLY A  33      -4.490  -5.830  -6.789  1.00 40.23           O  
ATOM    268  N   LEU A  34      -3.999  -4.165  -5.414  1.00 43.73           N  
ATOM    269  CA  LEU A  34      -2.683  -4.716  -5.104  1.00 41.85           C  
ATOM    270  C   LEU A  34      -2.773  -5.711  -3.963  1.00 43.43           C  
ATOM    271  O   LEU A  34      -2.075  -6.715  -3.936  1.00 41.45           O  
ATOM    272  CB  LEU A  34      -1.734  -3.583  -4.726  1.00 40.86           C  
ATOM    273  CG  LEU A  34      -1.394  -2.659  -5.887  1.00 38.87           C  
ATOM    274  CD1 LEU A  34      -0.693  -1.416  -5.386  1.00 36.71           C  
ATOM    275  CD2 LEU A  34      -0.523  -3.382  -6.893  1.00 37.12           C  
ATOM    276  N   PHE A  35      -3.594  -5.392  -3.003  1.00 39.46           N  
ATOM    277  CA  PHE A  35      -3.781  -6.274  -1.853  1.00 37.62           C  
ATOM    278  C   PHE A  35      -5.227  -6.764  -1.848  1.00 38.80           C  
ATOM    279  O   PHE A  35      -5.448  -7.952  -1.662  1.00 37.05           O  
ATOM    280  CB  PHE A  35      -3.504  -5.486  -0.567  1.00 37.36           C  
ATOM    281  CG  PHE A  35      -2.375  -4.513  -0.701  1.00 34.98           C  
ATOM    282  CD1 PHE A  35      -1.073  -4.958  -0.813  1.00 32.67           C  
ATOM    283  CD2 PHE A  35      -2.609  -3.146  -0.720  1.00 32.49           C  
ATOM    284  CE1 PHE A  35      -0.027  -4.068  -0.936  1.00 31.41           C  
ATOM    285  CE2 PHE A  35      -1.567  -2.245  -0.845  1.00 31.49           C  
ATOM    286  CZ  PHE A  35      -0.274  -2.710  -0.943  1.00 31.48           C  
CONECT    3    9
CONECT    9    3
CONECT   11   15
CONECT   15   11
CONECT   17   23
CONECT   23   17
CONECT   25   32
CONECT   32   25
CONECT   34   40
CONECT   40   34
CONECT   42   51
CONECT   51   42
CONECT   53   60
CONECT   60   53
CONECT   62   65
CONECT   65   62
CONECT   67   72
CONECT   72   67
CONECT   74   83
CONECT   83   74
CONECT   85   87
CONECT   87   85
CONECT   89   95
CONECT   95   89
CONECT   97  102
CONECT  102   97
CONECT  104  113
CONECT  113  104
CONECT  115  119
CONECT  119  115
CONECT  121  124
CONECT  124  121
CONECT  126  135
CONECT  135  126
CONECT  137  140
CONECT  140  137
CONECT  142  148
CONECT  148  142
CONECT  150  156
CONECT  156  150
CONECT  158  163
CONECT  163  158
CONECT  165  171
CONECT  171  165
CONECT  173  185
CONECT  185  173
CONECT  187  194
CONECT  194  187
CONECT  196  203
CONECT  203  196
CONECT  205  212
CONECT  212  205
CONECT  214  220
CONECT  220  214
CONECT  222  228
CONECT  228  222
CONECT  230  237
CONECT  237  230
CONECT  239  246
CONECT  246  239
CONECT  248  255
CONECT  255  248
CONECT  257  264
CONECT  264  257
CONECT  266  268
CONECT  268  266
CONECT  270  276
CONECT  276  270
`;

export const OPENFOLD3_EXAMPLE: PlaygroundResult = {
  type: 'structure',
  raw: { note: 'Example response (pre-computed)' },
  items: [
    {
      label: 'Predicted Structure (pLDDT: 48.8, pTM: 0.314)',
      value: OPENFOLD3_STRUCTURE,
      format: 'structure',
      downloadFilename: 'openfold3_prediction.pdb',
    },
  ],
};

// ============================================================================
// Boltz2 Example
// ============================================================================

const BOLTZ2_STRUCTURE = `data_model
_entry.id model
_struct.entry_id model
_struct.pdbx_model_details .
_struct.pdbx_structure_determination_methodology computational
_struct.title .
_audit_conform.dict_location https://raw.githubusercontent.com/ihmwg/ModelCIF/d18ba38/base/mmcif_ma-core.dic
_audit_conform.dict_name mmcif_ma.dic
_audit_conform.dict_version 1.4.6
#
loop_
_chem_comp.id
_chem_comp.type
_chem_comp.name
_chem_comp.formula
_chem_comp.formula_weight
_chem_comp.ma_provenance
ALA 'L-peptide linking' . . . 'CCD Core'
ARG 'L-peptide linking' . . . 'CCD Core'
ASN 'L-peptide linking' . . . 'CCD Core'
ASP 'L-peptide linking' . . . 'CCD Core'
GLN 'L-peptide linking' . . . 'CCD Core'
GLU 'L-peptide linking' . . . 'CCD Core'
GLY 'L-peptide linking' . . . 'CCD Core'
LEU 'L-peptide linking' . . . 'CCD Core'
LYS 'L-peptide linking' . . . 'CCD Core'
MET 'L-peptide linking' . . . 'CCD Core'
PHE 'L-peptide linking' . . . 'CCD Core'
PRO 'L-peptide linking' . . . 'CCD Core'
SER 'L-peptide linking' . . . 'CCD Core'
THR 'L-peptide linking' . . . 'CCD Core'
TRP 'L-peptide linking' . . . 'CCD Core'
VAL 'L-peptide linking' . . . 'CCD Core'
#
#
loop_
_entity.id
_entity.type
_entity.src_method
_entity.pdbx_description
_entity.formula_weight
_entity.pdbx_number_of_molecules
_entity.details
1 polymer man . . 1 .
#
#
loop_
_entity_poly.entity_id
_entity_poly.type
_entity_poly.nstd_linkage
_entity_poly.nstd_monomer
_entity_poly.pdbx_strand_id
_entity_poly.pdbx_seq_one_letter_code
_entity_poly.pdbx_seq_one_letter_code_can
1 polypeptide(L) no no A
;(LEU)(SER)(ASP)(GLU)(ASP)(PHE)(LYS)(ALA)(VAL)(PHE)(GLY)(MET)(THR)(ARG)
(SER)(ALA)(PHE)(ALA)(ASN)(LEU)(PRO)(LEU)(TRP)(LYS)(GLN)(GLN)(ASN)(LEU)
(LYS)(LYS)(GLU)(LYS)(GLY)(LEU)(PHE)
;
XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
#
#
loop_
_entity_poly_seq.entity_id
_entity_poly_seq.num
_entity_poly_seq.mon_id
_entity_poly_seq.hetero
1 1 LEU .
1 2 SER .
1 3 ASP .
1 4 GLU .
1 5 ASP .
1 6 PHE .
1 7 LYS .
1 8 ALA .
1 9 VAL .
1 10 PHE .
1 11 GLY .
1 12 MET .
1 13 THR .
1 14 ARG .
1 15 SER .
1 16 ALA .
1 17 PHE .
1 18 ALA .
1 19 ASN .
1 20 LEU .
1 21 PRO .
1 22 LEU .
1 23 TRP .
1 24 LYS .
1 25 GLN .
1 26 GLN .
1 27 ASN .
1 28 LEU .
1 29 LYS .
1 30 LYS .
1 31 GLU .
1 32 LYS .
1 33 GLY .
1 34 LEU .
1 35 PHE .
#
#
loop_
_struct_asym.id
_struct_asym.entity_id
_struct_asym.details
A 1 'Model subunit A'
#
#
loop_
_pdbx_poly_seq_scheme.asym_id
_pdbx_poly_seq_scheme.entity_id
_pdbx_poly_seq_scheme.seq_id
_pdbx_poly_seq_scheme.mon_id
_pdbx_poly_seq_scheme.pdb_seq_num
_pdbx_poly_seq_scheme.auth_seq_num
_pdbx_poly_seq_scheme.pdb_mon_id
_pdbx_poly_seq_scheme.auth_mon_id
_pdbx_poly_seq_scheme.pdb_strand_id
_pdbx_poly_seq_scheme.pdb_ins_code
A 1 1 LEU 1 1 LEU LEU A .
A 1 2 SER 2 2 SER SER A .
A 1 3 ASP 3 3 ASP ASP A .
A 1 4 GLU 4 4 GLU GLU A .
A 1 5 ASP 5 5 ASP ASP A .
A 1 6 PHE 6 6 PHE PHE A .
A 1 7 LYS 7 7 LYS LYS A .
A 1 8 ALA 8 8 ALA ALA A .
A 1 9 VAL 9 9 VAL VAL A .
A 1 10 PHE 10 10 PHE PHE A .
A 1 11 GLY 11 11 GLY GLY A .
A 1 12 MET 12 12 MET MET A .
A 1 13 THR 13 13 THR THR A .
A 1 14 ARG 14 14 ARG ARG A .
A 1 15 SER 15 15 SER SER A .
A 1 16 ALA 16 16 ALA ALA A .
A 1 17 PHE 17 17 PHE PHE A .
A 1 18 ALA 18 18 ALA ALA A .
A 1 19 ASN 19 19 ASN ASN A .
A 1 20 LEU 20 20 LEU LEU A .
A 1 21 PRO 21 21 PRO PRO A .
A 1 22 LEU 22 22 LEU LEU A .
A 1 23 TRP 23 23 TRP TRP A .
A 1 24 LYS 24 24 LYS LYS A .
A 1 25 GLN 25 25 GLN GLN A .
A 1 26 GLN 26 26 GLN GLN A .
A 1 27 ASN 27 27 ASN ASN A .
A 1 28 LEU 28 28 LEU LEU A .
A 1 29 LYS 29 29 LYS LYS A .
A 1 30 LYS 30 30 LYS LYS A .
A 1 31 GLU 31 31 GLU GLU A .
A 1 32 LYS 32 32 LYS LYS A .
A 1 33 GLY 33 33 GLY GLY A .
A 1 34 LEU 34 34 LEU LEU A .
A 1 35 PHE 35 35 PHE PHE A .
#
#
loop_
_ma_data.id
_ma_data.name
_ma_data.content_type
_ma_data.content_type_other_details
1 . target .
2 Model 'model coordinates' .
#
#
loop_
_ma_target_entity.entity_id
_ma_target_entity.data_id
_ma_target_entity.origin
1 1 designed
#
#
loop_
_ma_target_entity_instance.asym_id
_ma_target_entity_instance.entity_id
_ma_target_entity_instance.details
A 1 'Model subunit A'
#
#
loop_
_ma_model_list.ordinal_id
_ma_model_list.model_id
_ma_model_list.model_group_id
_ma_model_list.model_name
_ma_model_list.model_group_name
_ma_model_list.data_id
_ma_model_list.model_type
_ma_model_list.model_type_other_details
1 1 1 Model 'All models' 2 'Ab initio model' .
#
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_seq_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.label_asym_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.label_entity_id
_atom_site.auth_asym_id
_atom_site.auth_comp_id
_atom_site.B_iso_or_equiv
_atom_site.pdbx_PDB_model_num
ATOM 1 N N . LEU 1 1 ? A 2.13935 5.65073 -9.17488 1 1 A LEU 85.054 1
ATOM 2 C CA . LEU 1 1 ? A 1.97996 6.68900 -8.15292 1 1 A LEU 85.054 1
ATOM 3 C C . LEU 1 1 ? A 3.34234 7.15590 -7.65793 1 1 A LEU 85.054 1
ATOM 4 O O . LEU 1 1 ? A 4.24280 6.34500 -7.46236 1 1 A LEU 85.054 1
ATOM 5 C CB . LEU 1 1 ? A 1.18118 6.18140 -6.95063 1 1 A LEU 85.054 1
ATOM 6 C CG . LEU 1 1 ? A -0.25387 5.71910 -7.19296 1 1 A LEU 85.054 1
ATOM 7 C CD1 . LEU 1 1 ? A -0.81905 5.12250 -5.90945 1 1 A LEU 85.054 1
ATOM 8 C CD2 . LEU 1 1 ? A -1.10803 6.88059 -7.66759 1 1 A LEU 85.054 1
ATOM 9 N N . SER 2 2 ? A 3.47742 8.45987 -7.46274 1 1 A SER 96.340 1
ATOM 10 C CA . SER 2 2 ? A 4.65596 8.99205 -6.79486 1 1 A SER 96.340 1
ATOM 11 C C . SER 2 2 ? A 4.57267 8.61160 -5.31844 1 1 A SER 96.340 1
ATOM 12 O O . SER 2 2 ? A 3.52850 8.16534 -4.84027 1 1 A SER 96.340 1
ATOM 13 C CB . SER 2 2 ? A 4.71067 10.51826 -6.92152 1 1 A SER 96.340 1
ATOM 14 O OG . SER 2 2 ? A 3.65910 11.12728 -6.19299 1 1 A SER 96.340 1
ATOM 15 N N . ASP 3 3 ? A 5.67402 8.79066 -4.59394 1 1 A ASP 96.278 1
ATOM 16 C CA . ASP 3 3 ? A 5.65658 8.51746 -3.16128 1 1 A ASP 96.278 1
ATOM 17 C C . ASP 3 3 ? A 4.63461 9.39259 -2.45117 1 1 A ASP 96.278 1
ATOM 18 O O . ASP 3 3 ? A 3.94768 8.95058 -1.52682 1 1 A ASP 96.278 1
ATOM 19 C CB . ASP 3 3 ? A 7.04599 8.73352 -2.55518 1 1 A ASP 96.278 1
ATOM 20 C CG . ASP 3 3 ? A 8.03986 7.66212 -2.96503 1 1 A ASP 96.278 1
ATOM 21 O OD1 . ASP 3 3 ? A 7.60942 6.57520 -3.40942 1 1 A ASP 96.278 1
ATOM 22 O OD2 . ASP 3 3 ? A 9.25727 7.91071 -2.83638 1 1 A ASP 96.278 1
ATOM 23 N N . GLU 4 4 ? A 4.51940 10.64729 -2.89224 1 1 A GLU 97.382 1
ATOM 24 C CA . GLU 4 4 ? A 3.54289 11.55947 -2.30221 1 1 A GLU 97.382 1
ATOM 25 C C . GLU 4 4 ? A 2.11928 11.09059 -2.58991 1 1 A GLU 97.382 1
ATOM 26 O O . GLU 4 4 ? A 1.26125 11.09567 -1.70002 1 1 A GLU 97.382 1
ATOM 27 C CB . GLU 4 4 ? A 3.75784 12.97028 -2.83360 1 1 A GLU 97.382 1
ATOM 28 C CG . GLU 4 4 ? A 2.82283 14.00869 -2.23562 1 1 A GLU 97.382 1
ATOM 29 C CD . GLU 4 4 ? A 3.06708 15.41004 -2.76795 1 1 A GLU 97.382 1
ATOM 30 O OE1 . GLU 4 4 ? A 3.81624 15.55793 -3.75559 1 1 A GLU 97.382 1
ATOM 31 O OE2 . GLU 4 4 ? A 2.49965 16.36088 -2.19975 1 1 A GLU 97.382 1
ATOM 32 N N . ASP 5 5 ? A 1.86143 10.68538 -3.83153 1 1 A ASP 94.622 1
ATOM 33 C CA . ASP 5 5 ? A 0.53593 10.18733 -4.19338 1 1 A ASP 94.622 1
ATOM 34 C C . ASP 5 5 ? A 0.21151 8.90062 -3.45637 1 1 A ASP 94.622 1
ATOM 35 O O . ASP 5 5 ? A -0.92930 8.67994 -3.03906 1 1 A ASP 94.622 1
ATOM 36 C CB . ASP 5 5 ? A 0.43936 9.94501 -5.70540 1 1 A ASP 94.622 1
ATOM 37 C CG . ASP 5 5 ? A 0.45881 11.22151 -6.51710 1 1 A ASP 94.622 1
ATOM 38 O OD1 . ASP 5 5 ? A 0.11465 12.29327 -5.96617 1 1 A ASP 94.622 1
ATOM 39 O OD2 . ASP 5 5 ? A 0.80480 11.14676 -7.71399 1 1 A ASP 94.622 1
ATOM 40 N N . PHE 6 6 ? A 1.20313 8.02599 -3.31194 1 1 A PHE 96.157 1
ATOM 41 C CA . PHE 6 6 ? A 1.00337 6.76338 -2.60405 1 1 A PHE 96.157 1
ATOM 42 C C . PHE 6 6 ? A 0.55810 7.02116 -1.16942 1 1 A PHE 96.157 1
ATOM 43 O O . PHE 6 6 ? A -0.38115 6.39234 -0.66959 1 1 A PHE 96.157 1
ATOM 44 C CB . PHE 6 6 ? A 2.29522 5.94503 -2.61601 1 1 A PHE 96.157 1
ATOM 45 C CG . PHE 6 6 ? A 2.13965 4.55612 -2.05704 1 1 A PHE 96.157 1
ATOM 46 C CD1 . PHE 6 6 ? A 1.91328 3.47657 -2.90386 1 1 A PHE 96.157 1
ATOM 47 C CD2 . PHE 6 6 ? A 2.20798 4.32574 -0.69233 1 1 A PHE 96.157 1
ATOM 48 C CE1 . PHE 6 6 ? A 1.76360 2.19513 -2.39330 1 1 A PHE 96.157 1
ATOM 49 C CE2 . PHE 6 6 ? A 2.05727 3.04605 -0.17541 1 1 A PHE 96.157 1
ATOM 50 C CZ . PHE 6 6 ? A 1.83416 1.98626 -1.02992 1 1 A PHE 96.157 1
ATOM 51 N N . LYS 7 7 ? A 1.24122 7.95252 -0.49825 1 1 A LYS 97.758 1
ATOM 52 C CA . LYS 7 7 ? A 0.88375 8.28156 0.87745 1 1 A LYS 97.758 1
ATOM 53 C C . LYS 7 7 ? A -0.51117 8.89412 0.95251 1 1 A LYS 97.758 1
ATOM 54 O O . LYS 7 7 ? A -1.26605 8.63131 1.89436 1 1 A LYS 97.758 1
ATOM 55 C CB . LYS 7 7 ? A 1.91990 9.22548 1.48525 1 1 A LYS 97.758 1
ATOM 56 C CG . LYS 7 7 ? A 1.70192 9.50154 2.95925 1 1 A LYS 97.758 1
ATOM 57 C CD . LYS 7 7 ? A 2.80400 10.35377 3.55840 1 1 A LYS 97.758 1
ATOM 58 C CE . LYS 7 7 ? A 2.56183 10.60435 5.03534 1 1 A LYS 97.758 1
ATOM 59 N NZ . LYS 7 7 ? A 3.62735 11.45858 5.62812 1 1 A LYS 97.758 1
ATOM 60 N N . ALA 8 8 ? A -0.87800 9.70468 -0.03187 1 1 A ALA 96.035 1
ATOM 61 C CA . ALA 8 8 ? A -2.21095 10.30309 -0.06068 1 1 A ALA 96.035 1
ATOM 62 C C . ALA 8 8 ? A -3.29078 9.23053 -0.18391 1 1 A ALA 96.035 1
ATOM 63 O O . ALA 8 8 ? A -4.35306 9.33353 0.43721 1 1 A ALA 96.035 1
ATOM 64 C CB . ALA 8 8 ? A -2.32175 11.29898 -1.21054 1 1 A ALA 96.035 1
ATOM 65 N N . VAL 9 9 ? A -3.03463 8.21563 -0.99592 1 1 A VAL 95.309 1
ATOM 66 C CA . VAL 9 9 ? A -4.00851 7.14653 -1.20782 1 1 A VAL 95.309 1
ATOM 67 C C . VAL 9 9 ? A -4.10481 6.21963 -0.00112 1 1 A VAL 95.309 1
ATOM 68 O O . VAL 9 9 ? A -5.20579 5.91719 0.47385 1 1 A VAL 95.309 1
ATOM 69 C CB . VAL 9 9 ? A -3.66161 6.33313 -2.47267 1 1 A VAL 95.309 1
ATOM 70 C CG1 . VAL 9 9 ? A -4.52744 5.08056 -2.56764 1 1 A VAL 95.309 1
ATOM 71 C CG2 . VAL 9 9 ? A -3.83073 7.20319 -3.71319 1 1 A VAL 95.309 1
ATOM 72 N N . PHE 10 10 ? A -2.96792 5.73990 0.49088 1 1 A PHE 97.144 1
ATOM 73 C CA . PHE 10 10 ? A -2.94940 4.70231 1.51674 1 1 A PHE 97.144 1
ATOM 74 C C . PHE 10 10 ? A -2.77862 5.20442 2.94380 1 1 A PHE 97.144 1
ATOM 75 O O . PHE 10 10 ? A -2.96638 4.42585 3.88301 1 1 A PHE 97.144 1
ATOM 76 C CB . PHE 10 10 ? A -1.85217 3.68204 1.20668 1 1 A PHE 97.144 1
ATOM 77 C CG . PHE 10 10 ? A -2.16307 2.82749 0.00868 1 1 A PHE 97.144 1
ATOM 78 C CD1 . PHE 10 10 ? A -3.04467 1.76578 0.12527 1 1 A PHE 97.144 1
ATOM 79 C CD2 . PHE 10 10 ? A -1.58892 3.08169 -1.21979 1 1 A PHE 97.144 1
ATOM 80 C CE1 . PHE 10 10 ? A -3.34480 0.97196 -0.96481 1 1 A PHE 97.144 1
ATOM 81 C CE2 . PHE 10 10 ? A -1.87915 2.29565 -2.32050 1 1 A PHE 97.144 1
ATOM 82 C CZ . PHE 10 10 ? A -2.76240 1.24130 -2.18937 1 1 A PHE 97.144 1
ATOM 83 N N . GLY 11 11 ? A -2.41899 6.49516 3.11568 1 1 A GLY 97.300 1
ATOM 84 C CA . GLY 11 11 ? A -2.22599 7.02309 4.45026 1 1 A GLY 97.300 1
ATOM 85 C C . GLY 11 11 ? A -0.95287 6.54995 5.11507 1 1 A GLY 97.300 1
ATOM 86 O O . GLY 11 11 ? A -0.83540 6.61006 6.34353 1 1 A GLY 97.300 1
ATOM 87 N N . MET 12 12 ? A 0.00842 6.08035 4.34114 1 1 A MET 98.350 1
ATOM 88 C CA . MET 12 12 ? A 1.27840 5.60845 4.87280 1 1 A MET 98.350 1
ATOM 89 C C . MET 12 12 ? A 2.31825 5.63887 3.76764 1 1 A MET 98.350 1
ATOM 90 O O . MET 12 12 ? A 1.98477 5.76093 2.58664 1 1 A MET 98.350 1
ATOM 91 C CB . MET 12 12 ? A 1.15461 4.18321 5.42964 1 1 A MET 98.350 1
ATOM 92 C CG . MET 12 12 ? A 0.85368 3.11859 4.39498 1 1 A MET 98.350 1
ATOM 93 S SD . MET 12 12 ? A 0.56788 1.47509 5.13839 1 1 A MET 98.350 1
ATOM 94 C CE . MET 12 12 ? A -1.09675 1.70169 5.77755 1 1 A MET 98.350 1
ATOM 95 N N . THR 13 13 ? A 3.59818 5.53633 4.15509 1 1 A THR 98.390 1
ATOM 96 C CA . THR 13 13 ? A 4.68307 5.52245 3.18636 1 1 A THR 98.390 1
ATOM 97 C C . THR 13 13 ? A 4.78376 4.15118 2.53066 1 1 A THR 98.390 1
ATOM 98 O O . THR 13 13 ? A 4.24451 3.16125 3.02107 1 1 A THR 98.390 1
ATOM 99 C CB . THR 13 13 ? A 6.02987 5.84257 3.85013 1 1 A THR 98.390 1
ATOM 100 O OG1 . THR 13 13 ? A 6.34449 4.80551 4.78712 1 1 A THR 98.390 1
ATOM 101 C CG2 . THR 13 13 ? A 5.96419 7.18750 4.56362 1 1 A THR 98.390 1
ATOM 102 N N . ARG 14 14 ? A 5.50186 4.10128 1.40033 1 1 A ARG 96.712 1
ATOM 103 C CA . ARG 14 14 ? A 5.72416 2.82668 0.71828 1 1 A ARG 96.712 1
ATOM 104 C C . ARG 14 14 ? A 6.47312 1.84705 1.61143 1 1 A ARG 96.712 1
ATOM 105 O O . ARG 14 14 ? A 6.18304 0.65268 1.59909 1 1 A ARG 96.712 1
ATOM 106 C CB . ARG 14 14 ? A 6.50953 3.03076 -0.57464 1 1 A ARG 96.712 1
ATOM 107 C CG . ARG 14 14 ? A 5.71323 3.66700 -1.69788 1 1 A ARG 96.712 1
ATOM 108 C CD . ARG 14 14 ? A 6.54723 3.69506 -2.97031 1 1 A ARG 96.712 1
ATOM 109 N NE . ARG 14 14 ? A 5.84740 4.35574 -4.06804 1 1 A ARG 96.712 1
ATOM 110 C CZ . ARG 14 14 ? A 5.00204 3.75099 -4.89333 1 1 A ARG 96.712 1
ATOM 111 N NH1 . ARG 14 14 ? A 4.73424 2.45842 -4.75811 1 1 A ARG 96.712 1
ATOM 112 N NH2 . ARG 14 14 ? A 4.41934 4.45073 -5.86290 1 1 A ARG 96.712 1
ATOM 113 N N . SER 15 15 ? A 7.44591 2.33861 2.37475 1 1 A SER 97.940 1
ATOM 114 C CA . SER 15 15 ? A 8.21111 1.43578 3.22561 1 1 A SER 97.940 1
ATOM 115 C C . SER 15 15 ? A 7.33873 0.85700 4.33208 1 1 A SER 97.940 1
ATOM 116 O O . SER 15 15 ? A 7.47070 -0.31762 4.68289 1 1 A SER 97.940 1
ATOM 117 C CB . SER 15 15 ? A 9.43320 2.14239 3.81557 1 1 A SER 97.940 1
ATOM 118 O OG . SER 15 15 ? A 9.06384 3.21614 4.64923 1 1 A SER 97.940 1
ATOM 119 N N . ALA 16 16 ? A 6.42697 1.65698 4.89358 1 1 A ALA 98.685 1
ATOM 120 C CA . ALA 16 16 ? A 5.50534 1.15282 5.90526 1 1 A ALA 98.685 1
ATOM 121 C C . ALA 16 16 ? A 4.56733 0.11944 5.29149 1 1 A ALA 98.685 1
ATOM 122 O O . ALA 16 16 ? A 4.30380 -0.92752 5.88413 1 1 A ALA 98.685 1
ATOM 123 C CB . ALA 16 16 ? A 4.70659 2.29633 6.51921 1 1 A ALA 98.685 1
ATOM 124 N N . PHE 17 17 ? A 4.05705 0.40543 4.10207 1 1 A PHE 98.296 1
ATOM 125 C CA . PHE 17 17 ? A 3.16122 -0.50995 3.40386 1 1 A PHE 98.296 1
ATOM 126 C C . PHE 17 17 ? A 3.85728 -1.83713 3.10251 1 1 A PHE 98.296 1
ATOM 127 O O . PHE 17 17 ? A 3.28294 -2.90890 3.30754 1 1 A PHE 98.296 1
ATOM 128 C CB . PHE 17 17 ? A 2.68168 0.13960 2.10571 1 1 A PHE 98.296 1
ATOM 129 C CG . PHE 17 17 ? A 1.62287 -0.63817 1.37132 1 1 A PHE 98.296 1
ATOM 130 C CD1 . PHE 17 17 ? A 0.27554 -0.40818 1.62948 1 1 A PHE 98.296 1
ATOM 131 C CD2 . PHE 17 17 ? A 1.96995 -1.57845 0.41593 1 1 A PHE 98.296 1
ATOM 132 C CE1 . PHE 17 17 ? A -0.70775 -1.11149 0.94809 1 1 A PHE 98.296 1
ATOM 133 C CE2 . PHE 17 17 ? A 0.99136 -2.28961 -0.26891 1 1 A PHE 98.296 1
ATOM 134 C CZ . PHE 17 17 ? A -0.34265 -2.05316 0.00043 1 1 A PHE 98.296 1
ATOM 135 N N . ALA 18 18 ? A 5.10271 -1.75953 2.62801 1 1 A ALA 97.998 1
ATOM 136 C CA . ALA 18 18 ? A 5.84409 -2.95576 2.24823 1 1 A ALA 97.998 1
ATOM 137 C C . ALA 18 18 ? A 6.14058 -3.86189 3.43501 1 1 A ALA 97.998 1
ATOM 138 O O . ALA 18 18 ? A 6.37878 -5.05567 3.25471 1 1 A ALA 97.998 1
ATOM 139 C CB . ALA 18 18 ? A 7.14261 -2.57349 1.55281 1 1 A ALA 97.998 1
ATOM 140 N N . ASN 19 19 ? A 6.11777 -3.31119 4.64245 1 1 A ASN 98.533 1
ATOM 141 C CA . ASN 19 19 ? A 6.38218 -4.10054 5.83928 1 1 A ASN 98.533 1
ATOM 142 C C . ASN 19 19 ? A 5.13634 -4.75182 6.42460 1 1 A ASN 98.533 1
ATOM 143 O O . ASN 19 19 ? A 5.22860 -5.48318 7.41476 1 1 A ASN 98.533 1
ATOM 144 C CB . ASN 19 19 ? A 7.07802 -3.24008 6.89525 1 1 A ASN 98.533 1
ATOM 145 C CG . ASN 19 19 ? A 8.55424 -3.07498 6.60321 1 1 A ASN 98.533 1
ATOM 146 O OD1 . ASN 19 19 ? A 9.25748 -4.05569 6.37356 1 1 A ASN 98.533 1
ATOM 147 N ND2 . ASN 19 19 ? A 9.02856 -1.83849 6.61233 1 1 A ASN 98.533 1
ATOM 148 N N . LEU 20 20 ? A 3.97609 -4.50173 5.81963 1 1 A LEU 98.518 1
ATOM 149 C CA . LEU 20 20 ? A 2.75209 -5.16252 6.25059 1 1 A LEU 98.518 1
ATOM 150 C C . LEU 20 20 ? A 2.73022 -6.59098 5.70263 1 1 A LEU 98.518 1
ATOM 151 O O . LEU 20 20 ? A 3.36622 -6.88392 4.68968 1 1 A LEU 98.518 1
ATOM 152 C CB . LEU 20 20 ? A 1.51829 -4.42156 5.73287 1 1 A LEU 98.518 1
ATOM 153 C CG . LEU 20 20 ? A 1.31027 -2.99254 6.21430 1 1 A LEU 98.518 1
ATOM 154 C CD1 . LEU 20 20 ? A 0.14768 -2.35721 5.45212 1 1 A LEU 98.518 1
ATOM 155 C CD2 . LEU 20 20 ? A 1.04943 -2.96688 7.71184 1 1 A LEU 98.518 1
ATOM 156 N N . PRO 21 21 ? A 2.00173 -7.49333 6.36842 1 1 A PRO 98.451 1
ATOM 157 C CA . PRO 21 21 ? A 1.80680 -8.82639 5.79629 1 1 A PRO 98.451 1
ATOM 158 C C . PRO 21 21 ? A 1.14078 -8.70335 4.42680 1 1 A PRO 98.451 1
ATOM 159 O O . PRO 21 21 ? A 0.36688 -7.77072 4.18373 1 1 A PRO 98.451 1
ATOM 160 C CB . PRO 21 21 ? A 0.86998 -9.51521 6.79393 1 1 A PRO 98.451 1
ATOM 161 C CG . PRO 21 21 ? A 1.04230 -8.76801 8.06554 1 1 A PRO 98.451 1
ATOM 162 C CD . PRO 21 21 ? A 1.32389 -7.34182 7.66920 1 1 A PRO 98.451 1
ATOM 163 N N . LEU 22 22 ? A 1.42558 -9.64957 3.53856 1 1 A LEU 97.817 1
ATOM 164 C CA . LEU 22 22 ? A 0.89575 -9.58401 2.17556 1 1 A LEU 97.817 1
ATOM 165 C C . LEU 22 22 ? A -0.63021 -9.52386 2.15429 1 1 A LEU 97.817 1
ATOM 166 O O . LEU 22 22 ? A -1.21597 -8.77995 1.36836 1 1 A LEU 97.817 1
ATOM 167 C CB . LEU 22 22 ? A 1.39611 -10.77678 1.35350 1 1 A LEU 97.817 1
ATOM 168 C CG . LEU 22 22 ? A 0.94086 -10.82667 -0.10280 1 1 A LEU 97.817 1
ATOM 169 C CD1 . LEU 22 22 ? A 1.38283 -9.57409 -0.85830 1 1 A LEU 97.817 1
ATOM 170 C CD2 . LEU 22 22 ? A 1.48245 -12.08662 -0.77738 1 1 A LEU 97.817 1
ATOM 171 N N . TRP 23 23 ? A -1.29021 -10.29667 3.02759 1 1 A TRP 98.336 1
ATOM 172 C CA . TRP 23 23 ? A -2.74648 -10.28285 3.05053 1 1 A TRP 98.336 1
ATOM 173 C C . TRP 23 23 ? A -3.28244 -8.89795 3.37337 1 1 A TRP 98.336 1
ATOM 174 O O . TRP 23 23 ? A -4.30471 -8.47264 2.83170 1 1 A TRP 98.336 1
ATOM 175 C CB . TRP 23 23 ? A -3.29404 -11.32096 4.04662 1 1 A TRP 98.336 1
ATOM 176 C CG . TRP 23 23 ? A -2.97221 -11.03892 5.49391 1 1 A TRP 98.336 1
ATOM 177 C CD1 . TRP 23 23 ? A -1.93169 -11.53958 6.22244 1 1 A TRP 98.336 1
ATOM 178 C CD2 . TRP 23 23 ? A -3.71211 -10.19183 6.39682 1 1 A TRP 98.336 1
ATOM 179 N NE1 . TRP 23 23 ? A -1.97091 -11.05463 7.50992 1 1 A TRP 98.336 1
ATOM 180 C CE2 . TRP 23 23 ? A -3.04948 -10.22936 7.64211 1 1 A TRP 98.336 1
ATOM 181 C CE3 . TRP 23 23 ? A -4.88127 -9.42225 6.26087 1 1 A TRP 98.336 1
ATOM 182 C CZ2 . TRP 23 23 ? A -3.51182 -9.50912 8.74792 1 1 A TRP 98.336 1
ATOM 183 C CZ3 . TRP 23 23 ? A -5.33914 -8.71533 7.36432 1 1 A TRP 98.336 1
ATOM 184 C CH2 . TRP 23 23 ? A -4.66338 -8.76513 8.59294 1 1 A TRP 98.336 1
ATOM 185 N N . LYS 24 24 ? A -2.58764 -8.18398 4.24812 1 1 A LYS 98.061 1
ATOM 186 C CA . LYS 24 24 ? A -3.01218 -6.84038 4.62319 1 1 A LYS 98.061 1
ATOM 187 C C . LYS 24 24 ? A -2.79555 -5.87140 3.46696 1 1 A LYS 98.061 1
ATOM 188 O O . LYS 24 24 ? A -3.63855 -5.00430 3.20899 1 1 A LYS 98.061 1
ATOM 189 C CB . LYS 24 24 ? A -2.25924 -6.37163 5.86449 1 1 A LYS 98.061 1
ATOM 190 C CG . LYS 24 24 ? A -2.67381 -4.99577 6.36982 1 1 A LYS 98.061 1
ATOM 191 C CD . LYS 24 24 ? A -4.08033 -4.99152 6.94080 1 1 A LYS 98.061 1
ATOM 192 C CE . LYS 24 24 ? A -4.38656 -3.67629 7.64215 1 1 A LYS 98.061 1
ATOM 193 N NZ . LYS 24 24 ? A -5.74123 -3.67083 8.24108 1 1 A LYS 98.061 1
ATOM 194 N N . GLN 25 25 ? A -1.66069 -6.00460 2.76302 1 1 A GLN 97.710 1
ATOM 195 C CA . GLN 25 25 ? A -1.40459 -5.16905 1.59417 1 1 A GLN 97.710 1
ATOM 196 C C . GLN 25 25 ? A -2.50514 -5.35963 0.55706 1 1 A GLN 97.710 1
ATOM 197 O O . GLN 25 25 ? A -3.01063 -4.38921 -0.01621 1 1 A GLN 97.710 1
ATOM 198 C CB . GLN 25 25 ? A -0.05901 -5.52089 0.95413 1 1 A GLN 97.710 1
ATOM 199 C CG . GLN 25 25 ? A 1.15184 -5.26712 1.82975 1 1 A GLN 97.710 1
ATOM 200 C CD . GLN 25 25 ? A 2.43953 -5.59766 1.10319 1 1 A GLN 97.710 1
ATOM 201 O OE1 . GLN 25 25 ? A 2.53188 -5.47179 -0.12166 1 1 A GLN 97.710 1
ATOM 202 N NE2 . GLN 25 25 ? A 3.45238 -6.02829 1.84716 1 1 A GLN 97.710 1
ATOM 203 N N . GLN 26 26 ? A -2.87467 -6.61805 0.29339 1 1 A GLN 96.836 1
ATOM 204 C CA . GLN 26 26 ? A -3.88387 -6.90327 -0.71834 1 1 A GLN 96.836 1
ATOM 205 C C . GLN 26 26 ? A -5.25803 -6.38806 -0.29865 1 1 A GLN 96.836 1
ATOM 206 O O . GLN 26 26 ? A -6.00317 -5.86117 -1.12779 1 1 A GLN 96.836 1
ATOM 207 C CB . GLN 26 26 ? A -3.94074 -8.40464 -1.00800 1 1 A GLN 96.836 1
ATOM 208 C CG . GLN 26 26 ? A -2.66989 -8.94558 -1.64417 1 1 A GLN 96.836 1
ATOM 209 C CD . GLN 26 26 ? A -2.31856 -8.23097 -2.93368 1 1 A GLN 96.836 1
ATOM 210 O OE1 . GLN 26 26 ? A -3.17683 -8.02038 -3.79781 1 1 A GLN 96.836 1
ATOM 211 N NE2 . GLN 26 26 ? A -1.04991 -7.85775 -3.07777 1 1 A GLN 96.836 1
ATOM 212 N N . ASN 27 27 ? A -5.60120 -6.52361 0.97600 1 1 A ASN 97.705 1
ATOM 213 C CA . ASN 27 27 ? A -6.88408 -6.01117 1.44894 1 1 A ASN 97.705 1
ATOM 214 C C . ASN 27 27 ? A -6.95687 -4.49515 1.32342 1 1 A ASN 97.705 1
ATOM 215 O O . ASN 27 27 ? A -7.99565 -3.94319 0.95069 1 1 A ASN 97.705 1
ATOM 216 C CB . ASN 27 27 ? A -7.13433 -6.43001 2.89989 1 1 A ASN 97.705 1
ATOM 217 C CG . ASN 27 27 ? A -7.54146 -7.87920 3.02671 1 1 A ASN 97.705 1
ATOM 218 O OD1 . ASN 27 27 ? A -7.92200 -8.52555 2.04728 1 1 A ASN 97.705 1
ATOM 219 N ND2 . ASN 27 27 ? A -7.47587 -8.41142 4.24234 1 1 A ASN 97.705 1
ATOM 220 N N . LEU 28 28 ? A -5.85088 -3.81126 1.62707 1 1 A LEU 97.502 1
ATOM 221 C CA . LEU 28 28 ? A -5.83215 -2.35622 1.50417 1 1 A LEU 97.502 1
ATOM 222 C C . LEU 28 28 ? A -5.95965 -1.92556 0.04507 1 1 A LEU 97.502 1
ATOM 223 O O . LEU 28 28 ? A -6.63657 -0.94147 -0.25964 1 1 A LEU 97.502 1
ATOM 224 C CB . LEU 28 28 ? A -4.55457 -1.78414 2.12490 1 1 A LEU 97.502 1
ATOM 225 C CG . LEU 28 28 ? A -4.51304 -1.82711 3.65115 1 1 A LEU 97.502 1
ATOM 226 C CD1 . LEU 28 28 ? A -3.12281 -1.44699 4.15355 1 1 A LEU 97.502 1
ATOM 227 C CD2 . LEU 28 28 ? A -5.57167 -0.89203 4.24479 1 1 A LEU 97.502 1
ATOM 228 N N . LYS 29 29 ? A -5.31279 -2.65427 -0.86218 1 1 A LYS 95.796 1
ATOM 229 C CA . LYS 29 29 ? A -5.42248 -2.33385 -2.28166 1 1 A LYS 95.796 1
ATOM 230 C C . LYS 29 29 ? A -6.85453 -2.53450 -2.77418 1 1 A LYS 95.796 1
ATOM 231 O O . LYS 29 29 ? A -7.37052 -1.73503 -3.56102 1 1 A LYS 95.796 1
ATOM 232 C CB . LYS 29 29 ? A -4.45255 -3.18640 -3.10471 1 1 A LYS 95.796 1
ATOM 233 C CG . LYS 29 29 ? A -2.99691 -2.80197 -2.91502 1 1 A LYS 95.796 1
ATOM 234 C CD . LYS 29 29 ? A -2.07977 -3.71683 -3.71087 1 1 A LYS 95.796 1
ATOM 235 C CE . LYS 29 29 ? A -0.62843 -3.35930 -3.50232 1 1 A LYS 95.796 1
ATOM 236 N NZ . LYS 29 29 ? A 0.27028 -4.29250 -4.23043 1 1 A LYS 95.796 1
ATOM 237 N N . LYS 30 30 ? A -7.50628 -3.59649 -2.31245 1 1 A LYS 96.575 1
ATOM 238 C CA . LYS 30 30 ? A -8.89575 -3.84660 -2.69542 1 1 A LYS 96.575 1
ATOM 239 C C . LYS 30 30 ? A -9.80255 -2.73954 -2.17171 1 1 A LYS 96.575 1
ATOM 240 O O . LYS 30 30 ? A -10.70930 -2.28310 -2.87781 1 1 A LYS 96.575 1
ATOM 241 C CB . LYS 30 30 ? A -9.35432 -5.20869 -2.16971 1 1 A LYS 96.575 1
ATOM 242 C CG . LYS 30 30 ? A -8.69815 -6.37939 -2.87704 1 1 A LYS 96.575 1
ATOM 243 C CD . LYS 30 30 ? A -9.08752 -7.70637 -2.24467 1 1 A LYS 96.575 1
ATOM 244 C CE . LYS 30 30 ? A -8.35390 -8.86281 -2.89545 1 1 A LYS 96.575 1
ATOM 245 N NZ . LYS 30 30 ? A -8.69010 -10.15632 -2.24054 1 1 A LYS 96.575 1
ATOM 246 N N . GLU 31 31 ? A -9.54976 -2.30793 -0.93873 1 1 A GLU 95.462 1
ATOM 247 C CA . GLU 31 31 ? A -10.33786 -1.23493 -0.34344 1 1 A GLU 95.462 1
ATOM 248 C C . GLU 31 31 ? A -10.24724 0.03953 -1.17840 1 1 A GLU 95.462 1
ATOM 249 O O . GLU 31 31 ? A -11.22508 0.78582 -1.29562 1 1 A GLU 95.462 1
ATOM 250 C CB . GLU 31 31 ? A -9.85580 -0.96382 1.07941 1 1 A GLU 95.462 1
ATOM 251 C CG . GLU 31 31 ? A -10.55681 0.19317 1.77766 1 1 A GLU 95.462 1
ATOM 252 C CD . GLU 31 31 ? A -9.94981 0.51268 3.13088 1 1 A GLU 95.462 1
ATOM 253 O OE1 . GLU 31 31 ? A -9.19196 -0.31700 3.67239 1 1 A GLU 95.462 1
ATOM 254 O OE2 . GLU 31 31 ? A -10.23892 1.60807 3.66345 1 1 A GLU 95.462 1
ATOM 255 N N . LYS 32 32 ? A -9.07398 0.30647 -1.75264 1 1 A LYS 93.672 1
ATOM 256 C CA . LYS 32 32 ? A -8.85314 1.50591 -2.54775 1 1 A LYS 93.672 1
ATOM 257 C C . LYS 32 32 ? A -9.23798 1.31906 -4.01567 1 1 A LYS 93.672 1
ATOM 258 O O . LYS 32 32 ? A -9.03177 2.23012 -4.82088 1 1 A LYS 93.672 1
ATOM 259 C CB . LYS 32 32 ? A -7.39207 1.94924 -2.44910 1 1 A LYS 93.672 1
ATOM 260 C CG . LYS 32 32 ? A -6.93341 2.23901 -1.02699 1 1 A LYS 93.672 1
ATOM 261 C CD . LYS 32 32 ? A -7.72307 3.37281 -0.39339 1 1 A LYS 93.672 1
ATOM 262 C CE . LYS 32 32 ? A -7.21439 3.66995 1.00185 1 1 A LYS 93.672 1
ATOM 263 N NZ . LYS 32 32 ? A -8.01500 4.73252 1.66817 1 1 A LYS 93.672 1
ATOM 264 N N . GLY 33 33 ? A -9.77992 0.16199 -4.36592 1 1 A GLY 91.357 1
ATOM 265 C CA . GLY 33 33 ? A -10.21855 -0.08963 -5.72370 1 1 A GLY 91.357 1
ATOM 266 C C . GLY 33 33 ? A -9.09849 -0.38869 -6.70110 1 1 A GLY 91.357 1
ATOM 267 O O . GLY 33 33 ? A -9.27837 -0.22846 -7.91697 1 1 A GLY 91.357 1
ATOM 268 N N . LEU 34 34 ? A -7.95872 -0.83025 -6.20469 1 1 A LEU 89.088 1
ATOM 269 C CA . LEU 34 34 ? A -6.80948 -1.11633 -7.05357 1 1 A LEU 89.088 1
ATOM 270 C C . LEU 34 34 ? A -6.71502 -2.59120 -7.42859 1 1 A LEU 89.088 1
ATOM 271 O O . LEU 34 34 ? A -5.81095 -2.98310 -8.16898 1 1 A LEU 89.088 1
ATOM 272 C CB . LEU 34 34 ? A -5.52104 -0.65203 -6.37093 1 1 A LEU 89.088 1
ATOM 273 C CG . LEU 34 34 ? A -5.48628 0.83843 -6.03325 1 1 A LEU 89.088 1
ATOM 274 C CD1 . LEU 34 34 ? A -4.18529 1.20284 -5.33254 1 1 A LEU 89.088 1
ATOM 275 C CD2 . LEU 34 34 ? A -5.67861 1.67280 -7.28900 1 1 A LEU 89.088 1
ATOM 276 N N . PHE 35 35 ? A -7.63436 -3.40610 -6.91720 1 1 A PHE 71.627 1
ATOM 277 C CA . PHE 35 35 ? A -7.78227 -4.81619 -7.28425 1 1 A PHE 71.627 1
ATOM 278 C C . PHE 35 35 ? A -9.25495 -5.16423 -7.33045 1 1 A PHE 71.627 1
ATOM 279 O O . PHE 35 35 ? A -10.07223 -4.48212 -6.71154 1 1 A PHE 71.627 1
ATOM 280 C CB . PHE 35 35 ? A -7.07817 -5.73787 -6.27476 1 1 A PHE 71.627 1
ATOM 281 C CG . PHE 35 35 ? A -5.60776 -5.91343 -6.52778 1 1 A PHE 71.627 1
ATOM 282 C CD1 . PHE 35 35 ? A -5.14009 -6.97633 -7.28466 1 1 A PHE 71.627 1
ATOM 283 C CD2 . PHE 35 35 ? A -4.69636 -5.01456 -6.00728 1 1 A PHE 71.627 1
ATOM 284 C CE1 . PHE 35 35 ? A -3.78483 -7.14117 -7.51763 1 1 A PHE 71.627 1
ATOM 285 C CE2 . PHE 35 35 ? A -3.33663 -5.16597 -6.23704 1 1 A PHE 71.627 1
ATOM 286 C CZ . PHE 35 35 ? A -2.88132 -6.23247 -6.99460 1 1 A PHE 71.627 1
#
#
loop_
_atom_type.symbol
C
N
O
S
#
#
loop_
_ma_qa_metric.id
_ma_qa_metric.name
_ma_qa_metric.description
_ma_qa_metric.type
_ma_qa_metric.mode
_ma_qa_metric.type_other_details
_ma_qa_metric.software_group_id
1 pLDDT 'Predicted lddt' pLDDT local . .
#
#
loop_
_ma_qa_metric_local.ordinal_id
_ma_qa_metric_local.model_id
_ma_qa_metric_local.label_asym_id
_ma_qa_metric_local.label_seq_id
_ma_qa_metric_local.label_comp_id
_ma_qa_metric_local.metric_id
_ma_qa_metric_local.metric_value
1 1 A 1 LEU 1 85.054
2 1 A 2 SER 1 96.340
3 1 A 3 ASP 1 96.278
4 1 A 4 GLU 1 97.382
5 1 A 5 ASP 1 94.622
6 1 A 6 PHE 1 96.157
7 1 A 7 LYS 1 97.758
8 1 A 8 ALA 1 96.035
9 1 A 9 VAL 1 95.309
10 1 A 10 PHE 1 97.144
11 1 A 11 GLY 1 97.300
12 1 A 12 MET 1 98.350
13 1 A 13 THR 1 98.390
14 1 A 14 ARG 1 96.712
15 1 A 15 SER 1 97.940
16 1 A 16 ALA 1 98.685
17 1 A 17 PHE 1 98.296
18 1 A 18 ALA 1 97.998
19 1 A 19 ASN 1 98.533
20 1 A 20 LEU 1 98.518
21 1 A 21 PRO 1 98.451
22 1 A 22 LEU 1 97.817
23 1 A 23 TRP 1 98.336
24 1 A 24 LYS 1 98.061
25 1 A 25 GLN 1 97.710
26 1 A 26 GLN 1 96.836
27 1 A 27 ASN 1 97.705
28 1 A 28 LEU 1 97.502
29 1 A 29 LYS 1 95.796
30 1 A 30 LYS 1 96.575
31 1 A 31 GLU 1 95.462
32 1 A 32 LYS 1 93.672
33 1 A 33 GLY 1 91.357
34 1 A 34 LEU 1 89.088
35 1 A 35 PHE 1 71.627
#
`;

export const BOLTZ2_EXAMPLE: PlaygroundResult = {
  type: 'structure',
  raw: { note: 'Example response (pre-computed)' },
  items: [
    {
      label: 'Predicted Structure (pLDDT: 95.7, confidence: 0.933, pTM: 0.836)',
      value: BOLTZ2_STRUCTURE,
      format: 'structure',
      downloadFilename: 'boltz2_prediction.cif',
    },
  ],
};

// ============================================================================
// OpenFold2 Example
// ============================================================================

const OPENFOLD2_STRUCTURE = `REMARK no_recycling=3, max_templates=4, config_preset=model_3                   
PARENT N/A                                                                      
MODEL     1                                                                     
ATOM      1  N   LEU A   1      16.951  12.034 -13.573  1.00 78.11           N  
ATOM      2  CA  LEU A   1      16.833  11.082 -12.474  1.00 78.11           C  
ATOM      3  C   LEU A   1      16.789   9.650 -12.997  1.00 78.11           C  
ATOM      4  CB  LEU A   1      15.580  11.373 -11.644  1.00 78.11           C  
ATOM      5  O   LEU A   1      16.001   9.336 -13.893  1.00 78.11           O  
ATOM      6  CG  LEU A   1      15.812  11.862 -10.213  1.00 78.11           C  
ATOM      7  CD1 LEU A   1      15.098  13.190  -9.984  1.00 78.11           C  
ATOM      8  CD2 LEU A   1      15.343  10.816  -9.208  1.00 78.11           C  
ATOM      9  N   SER A   2      17.845   8.862 -12.860  1.00 86.98           N  
ATOM     10  CA  SER A   2      18.123   7.513 -13.341  1.00 86.98           C  
ATOM     11  C   SER A   2      17.295   6.476 -12.588  1.00 86.98           C  
ATOM     12  CB  SER A   2      19.610   7.188 -13.201  1.00 86.98           C  
ATOM     13  O   SER A   2      16.795   6.749 -11.495  1.00 86.98           O  
ATOM     14  OG  SER A   2      20.399   8.128 -13.911  1.00 86.98           O  
ATOM     15  N   ASP A   3      16.687   5.541 -13.225  1.00 92.68           N  
ATOM     16  CA  ASP A   3      15.961   4.386 -12.705  1.00 92.68           C  
ATOM     17  C   ASP A   3      16.570   3.900 -11.392  1.00 92.68           C  
ATOM     18  CB  ASP A   3      15.950   3.252 -13.732  1.00 92.68           C  
ATOM     19  O   ASP A   3      15.848   3.476 -10.486  1.00 92.68           O  
ATOM     20  CG  ASP A   3      15.111   3.569 -14.957  1.00 92.68           C  
ATOM     21  OD1 ASP A   3      13.995   4.113 -14.808  1.00 92.68           O  
ATOM     22  OD2 ASP A   3      15.568   3.269 -16.081  1.00 92.68           O  
ATOM     23  N   GLU A   4      17.875   4.052 -11.168  1.00 92.54           N  
ATOM     24  CA  GLU A   4      18.558   3.565  -9.973  1.00 92.54           C  
ATOM     25  C   GLU A   4      18.215   4.419  -8.756  1.00 92.54           C  
ATOM     26  CB  GLU A   4      20.073   3.544 -10.190  1.00 92.54           C  
ATOM     27  O   GLU A   4      18.068   3.900  -7.648  1.00 92.54           O  
ATOM     28  CG  GLU A   4      20.545   2.435 -11.121  1.00 92.54           C  
ATOM     29  CD  GLU A   4      22.057   2.376 -11.264  1.00 92.54           C  
ATOM     30  OE1 GLU A   4      22.698   1.531 -10.598  1.00 92.54           O  
ATOM     31  OE2 GLU A   4      22.607   3.181 -12.049  1.00 92.54           O  
ATOM     32  N   ASP A   5      18.147   5.773  -9.040  1.00 91.41           N  
ATOM     33  CA  ASP A   5      17.772   6.655  -7.940  1.00 91.41           C  
ATOM     34  C   ASP A   5      16.333   6.400  -7.497  1.00 91.41           C  
ATOM     35  CB  ASP A   5      17.946   8.121  -8.343  1.00 91.41           C  
ATOM     36  O   ASP A   5      16.031   6.431  -6.302  1.00 91.41           O  
ATOM     37  CG  ASP A   5      19.402   8.534  -8.465  1.00 91.41           C  
ATOM     38  OD1 ASP A   5      20.227   8.118  -7.622  1.00 91.41           O  
ATOM     39  OD2 ASP A   5      19.729   9.283  -9.411  1.00 91.41           O  
ATOM     40  N   PHE A   6      15.497   6.096  -8.525  1.00 91.82           N  
ATOM     41  CA  PHE A   6      14.100   5.817  -8.213  1.00 91.82           C  
ATOM     42  C   PHE A   6      13.973   4.541  -7.389  1.00 91.82           C  
ATOM     43  CB  PHE A   6      13.275   5.695  -9.498  1.00 91.82           C  
ATOM     44  O   PHE A   6      13.224   4.500  -6.411  1.00 91.82           O  
ATOM     45  CG  PHE A   6      12.758   7.011 -10.014  1.00 91.82           C  
ATOM     46  CD1 PHE A   6      11.536   7.512  -9.581  1.00 91.82           C  
ATOM     47  CD2 PHE A   6      13.494   7.748 -10.933  1.00 91.82           C  
ATOM     48  CE1 PHE A   6      11.055   8.729 -10.056  1.00 91.82           C  
ATOM     49  CE2 PHE A   6      13.019   8.965 -11.413  1.00 91.82           C  
ATOM     50  CZ  PHE A   6      11.799   9.453 -10.974  1.00 91.82           C  
ATOM     51  N   LYS A   7      14.772   3.558  -7.704  1.00 92.31           N  
ATOM     52  CA  LYS A   7      14.754   2.287  -6.986  1.00 92.31           C  
ATOM     53  C   LYS A   7      15.296   2.448  -5.569  1.00 92.31           C  
ATOM     54  CB  LYS A   7      15.564   1.232  -7.741  1.00 92.31           C  
ATOM     55  O   LYS A   7      14.773   1.849  -4.627  1.00 92.31           O  
ATOM     56  CG  LYS A   7      15.424  -0.175  -7.179  1.00 92.31           C  
ATOM     57  CD  LYS A   7      16.137  -1.199  -8.053  1.00 92.31           C  
ATOM     58  CE  LYS A   7      16.033  -2.602  -7.470  1.00 92.31           C  
ATOM     59  NZ  LYS A   7      16.733  -3.609  -8.321  1.00 92.31           N  
ATOM     60  N   ALA A   8      16.238   3.338  -5.541  1.00 93.77           N  
ATOM     61  CA  ALA A   8      16.819   3.585  -4.224  1.00 93.77           C  
ATOM     62  C   ALA A   8      15.802   4.230  -3.287  1.00 93.77           C  
ATOM     63  CB  ALA A   8      18.059   4.468  -4.347  1.00 93.77           C  
ATOM     64  O   ALA A   8      15.668   3.823  -2.131  1.00 93.77           O  
ATOM     65  N   VAL A   9      15.064   5.208  -3.760  1.00 91.83           N  
ATOM     66  CA  VAL A   9      14.069   5.913  -2.959  1.00 91.83           C  
ATOM     67  C   VAL A   9      12.938   4.959  -2.583  1.00 91.83           C  
ATOM     68  CB  VAL A   9      13.504   7.141  -3.708  1.00 91.83           C  
ATOM     69  O   VAL A   9      12.507   4.922  -1.428  1.00 91.83           O  
ATOM     70  CG1 VAL A   9      12.374   7.787  -2.908  1.00 91.83           C  
ATOM     71  CG2 VAL A   9      14.613   8.154  -3.985  1.00 91.83           C  
ATOM     72  N   PHE A  10      12.484   4.189  -3.576  1.00 91.82           N  
ATOM     73  CA  PHE A  10      11.422   3.224  -3.320  1.00 91.82           C  
ATOM     74  C   PHE A  10      11.859   2.203  -2.275  1.00 91.82           C  
ATOM     75  CB  PHE A  10      11.018   2.510  -4.614  1.00 91.82           C  
ATOM     76  O   PHE A  10      11.084   1.847  -1.385  1.00 91.82           O  
ATOM     77  CG  PHE A  10       9.881   3.173  -5.343  1.00 91.82           C  
ATOM     78  CD1 PHE A  10       8.563   2.912  -4.989  1.00 91.82           C  
ATOM     79  CD2 PHE A  10      10.131   4.059  -6.384  1.00 91.82           C  
ATOM     80  CE1 PHE A  10       7.509   3.525  -5.663  1.00 91.82           C  
ATOM     81  CE2 PHE A  10       9.083   4.675  -7.061  1.00 91.82           C  
ATOM     82  CZ  PHE A  10       7.773   4.406  -6.700  1.00 91.82           C  
ATOM     83  N   GLY A  11      13.017   1.696  -2.412  1.00 94.24           N  
ATOM     84  CA  GLY A  11      13.557   0.771  -1.428  1.00 94.24           C  
ATOM     85  C   GLY A  11      13.617   1.356  -0.029  1.00 94.24           C  
ATOM     86  O   GLY A  11      13.235   0.699   0.941  1.00 94.24           O  
ATOM     87  N   MET A  12      14.045   2.581   0.005  1.00 94.28           N  
ATOM     88  CA  MET A  12      14.190   3.248   1.296  1.00 94.28           C  
ATOM     89  C   MET A  12      12.828   3.497   1.934  1.00 94.28           C  
ATOM     90  CB  MET A  12      14.943   4.569   1.138  1.00 94.28           C  
ATOM     91  O   MET A  12      12.652   3.282   3.135  1.00 94.28           O  
ATOM     92  CG  MET A  12      16.429   4.399   0.867  1.00 94.28           C  
ATOM     93  SD  MET A  12      17.343   5.989   0.937  1.00 94.28           S  
ATOM     94  CE  MET A  12      16.954   6.654  -0.706  1.00 94.28           C  
ATOM     95  N   THR A  13      11.896   3.982   1.136  1.00 90.48           N  
ATOM     96  CA  THR A  13      10.555   4.270   1.632  1.00 90.48           C  
ATOM     97  C   THR A  13       9.873   2.995   2.118  1.00 90.48           C  
ATOM     98  CB  THR A  13       9.690   4.937   0.546  1.00 90.48           C  
ATOM     99  O   THR A  13       9.187   3.004   3.143  1.00 90.48           O  
ATOM    100  CG2 THR A  13       8.320   5.322   1.094  1.00 90.48           C  
ATOM    101  OG1 THR A  13      10.352   6.116   0.073  1.00 90.48           O  
ATOM    102  N   ARG A  14       9.972   1.886   1.275  1.00 92.01           N  
ATOM    103  CA  ARG A  14       9.434   0.586   1.663  1.00 92.01           C  
ATOM    104  C   ARG A  14       9.992   0.143   3.011  1.00 92.01           C  
ATOM    105  CB  ARG A  14       9.746  -0.465   0.596  1.00 92.01           C  
ATOM    106  O   ARG A  14       9.254  -0.364   3.858  1.00 92.01           O  
ATOM    107  CG  ARG A  14       9.151  -1.833   0.886  1.00 92.01           C  
ATOM    108  CD  ARG A  14       9.343  -2.792  -0.281  1.00 92.01           C  
ATOM    109  NE  ARG A  14       8.681  -4.071  -0.043  1.00 92.01           N  
ATOM    110  NH1 ARG A  14       9.949  -5.247  -1.574  1.00 92.01           N  
ATOM    111  NH2 ARG A  14       8.317  -6.315  -0.369  1.00 92.01           N  
ATOM    112  CZ  ARG A  14       8.984  -5.208  -0.663  1.00 92.01           C  
ATOM    113  N   SER A  15      11.249   0.381   3.206  1.00 92.19           N  
ATOM    114  CA  SER A  15      11.919  -0.009   4.442  1.00 92.19           C  
ATOM    115  C   SER A  15      11.407   0.801   5.628  1.00 92.19           C  
ATOM    116  CB  SER A  15      13.433   0.166   4.310  1.00 92.19           C  
ATOM    117  O   SER A  15      11.182   0.254   6.710  1.00 92.19           O  
ATOM    118  OG  SER A  15      13.958  -0.718   3.334  1.00 92.19           O  
ATOM    119  N   ALA A  16      11.262   2.023   5.431  1.00 90.62           N  
ATOM    120  CA  ALA A  16      10.770   2.902   6.489  1.00 90.62           C  
ATOM    121  C   ALA A  16       9.339   2.543   6.879  1.00 90.62           C  
ATOM    122  CB  ALA A  16      10.849   4.361   6.049  1.00 90.62           C  
ATOM    123  O   ALA A  16       8.990   2.550   8.062  1.00 90.62           O  
ATOM    124  N   PHE A  17       8.524   2.194   5.899  1.00 89.86           N  
ATOM    125  CA  PHE A  17       7.134   1.817   6.128  1.00 89.86           C  
ATOM    126  C   PHE A  17       7.048   0.525   6.932  1.00 89.86           C  
ATOM    127  CB  PHE A  17       6.393   1.656   4.797  1.00 89.86           C  
ATOM    128  O   PHE A  17       6.214   0.402   7.832  1.00 89.86           O  
ATOM    129  CG  PHE A  17       4.930   1.337   4.951  1.00 89.86           C  
ATOM    130  CD1 PHE A  17       4.474   0.030   4.834  1.00 89.86           C  
ATOM    131  CD2 PHE A  17       4.011   2.345   5.212  1.00 89.86           C  
ATOM    132  CE1 PHE A  17       3.120  -0.268   4.976  1.00 89.86           C  
ATOM    133  CE2 PHE A  17       2.658   2.055   5.355  1.00 89.86           C  
ATOM    134  CZ  PHE A  17       2.214   0.748   5.236  1.00 89.86           C  
ATOM    135  N   ALA A  18       8.010  -0.429   6.635  1.00 89.14           N  
ATOM    136  CA  ALA A  18       8.020  -1.702   7.351  1.00 89.14           C  
ATOM    137  C   ALA A  18       8.374  -1.501   8.822  1.00 89.14           C  
ATOM    138  CB  ALA A  18       9.002  -2.672   6.699  1.00 89.14           C  
ATOM    139  O   ALA A  18       8.000  -2.312   9.673  1.00 89.14           O  
ATOM    140  N   ASN A  19       9.044  -0.470   9.032  1.00 91.94           N  
ATOM    141  CA  ASN A  19       9.458  -0.251  10.414  1.00 91.94           C  
ATOM    142  C   ASN A  19       8.380   0.476  11.213  1.00 91.94           C  
ATOM    143  CB  ASN A  19      10.773   0.529  10.464  1.00 91.94           C  
ATOM    144  O   ASN A  19       8.591   0.820  12.378  1.00 91.94           O  
ATOM    145  CG  ASN A  19      11.966  -0.310  10.047  1.00 91.94           C  
ATOM    146  ND2 ASN A  19      12.880   0.292   9.296  1.00 91.94           N  
ATOM    147  OD1 ASN A  19      12.064  -1.489  10.398  1.00 91.94           O  
ATOM    148  N   LEU A  20       7.278   0.913  10.647  1.00 90.57           N  
ATOM    149  CA  LEU A  20       6.222   1.563  11.415  1.00 90.57           C  
ATOM    150  C   LEU A  20       5.481   0.552  12.284  1.00 90.57           C  
ATOM    151  CB  LEU A  20       5.236   2.269  10.480  1.00 90.57           C  
ATOM    152  O   LEU A  20       5.411  -0.631  11.945  1.00 90.57           O  
ATOM    153  CG  LEU A  20       5.785   3.456   9.687  1.00 90.57           C  
ATOM    154  CD1 LEU A  20       4.761   3.926   8.660  1.00 90.57           C  
ATOM    155  CD2 LEU A  20       6.170   4.594  10.626  1.00 90.57           C  
ATOM    156  N   PRO A  21       5.229   0.911  13.499  1.00 92.43           N  
ATOM    157  CA  PRO A  21       4.367   0.039  14.300  1.00 92.43           C  
ATOM    158  C   PRO A  21       3.110  -0.397  13.550  1.00 92.43           C  
ATOM    159  CB  PRO A  21       4.008   0.910  15.506  1.00 92.43           C  
ATOM    160  O   PRO A  21       2.654   0.303  12.642  1.00 92.43           O  
ATOM    161  CG  PRO A  21       4.937   2.078  15.425  1.00 92.43           C  
ATOM    162  CD  PRO A  21       5.499   2.145  14.034  1.00 92.43           C  
ATOM    163  N   LEU A  22       2.649  -1.633  13.683  1.00 89.33           N  
ATOM    164  CA  LEU A  22       1.512  -2.265  13.022  1.00 89.33           C  
ATOM    165  C   LEU A  22       0.277  -1.374  13.094  1.00 89.33           C  
ATOM    166  CB  LEU A  22       1.212  -3.626  13.656  1.00 89.33           C  
ATOM    167  O   LEU A  22      -0.511  -1.320  12.147  1.00 89.33           O  
ATOM    168  CG  LEU A  22       2.202  -4.750  13.349  1.00 89.33           C  
ATOM    169  CD1 LEU A  22       1.843  -6.003  14.141  1.00 89.33           C  
ATOM    170  CD2 LEU A  22       2.230  -5.046  11.854  1.00 89.33           C  
ATOM    171  N   TRP A  23       0.010  -0.616  14.240  1.00 91.15           N  
ATOM    172  CA  TRP A  23      -1.163   0.244  14.364  1.00 91.15           C  
ATOM    173  C   TRP A  23      -1.094   1.404  13.376  1.00 91.15           C  
ATOM    174  CB  TRP A  23      -1.289   0.781  15.792  1.00 91.15           C  
ATOM    175  O   TRP A  23      -2.124   1.867  12.881  1.00 91.15           O  
ATOM    176  CG  TRP A  23      -0.093   1.555  16.260  1.00 91.15           C  
ATOM    177  CD1 TRP A  23       1.054   1.049  16.805  1.00 91.15           C  
ATOM    178  CD2 TRP A  23       0.070   2.976  16.227  1.00 91.15           C  
ATOM    179  CE2 TRP A  23       1.343   3.263  16.769  1.00 91.15           C  
ATOM    180  CE3 TRP A  23      -0.737   4.036  15.792  1.00 91.15           C  
ATOM    181  NE1 TRP A  23       1.922   2.071  17.113  1.00 91.15           N  
ATOM    182  CH2 TRP A  23       1.018   5.586  16.452  1.00 91.15           C  
ATOM    183  CZ2 TRP A  23       1.827   4.568  16.886  1.00 91.15           C  
ATOM    184  CZ3 TRP A  23      -0.253   5.334  15.909  1.00 91.15           C  
ATOM    185  N   LYS A  24       0.162   1.886  13.221  1.00 89.86           N  
ATOM    186  CA  LYS A  24       0.358   2.946  12.237  1.00 89.86           C  
ATOM    187  C   LYS A  24       0.173   2.418  10.817  1.00 89.86           C  
ATOM    188  CB  LYS A  24       1.747   3.568  12.387  1.00 89.86           C  
ATOM    189  O   LYS A  24      -0.379   3.111   9.959  1.00 89.86           O  
ATOM    190  CG  LYS A  24       1.847   4.597  13.503  1.00 89.86           C  
ATOM    191  CD  LYS A  24       3.158   5.369  13.436  1.00 89.86           C  
ATOM    192  CE  LYS A  24       3.302   6.331  14.608  1.00 89.86           C  
ATOM    193  NZ  LYS A  24       4.569   7.117  14.527  1.00 89.86           N  
ATOM    194  N   GLN A  25       0.726   1.178  10.581  1.00 89.88           N  
ATOM    195  CA  GLN A  25       0.557   0.530   9.284  1.00 89.88           C  
ATOM    196  C   GLN A  25      -0.919   0.300   8.972  1.00 89.88           C  
ATOM    197  CB  GLN A  25       1.314  -0.798   9.245  1.00 89.88           C  
ATOM    198  O   GLN A  25      -1.356   0.491   7.835  1.00 89.88           O  
ATOM    199  CG  GLN A  25       2.828  -0.645   9.315  1.00 89.88           C  
ATOM    200  CD  GLN A  25       3.560  -1.963   9.145  1.00 89.88           C  
ATOM    201  NE2 GLN A  25       4.634  -1.948   8.364  1.00 89.88           N  
ATOM    202  OE1 GLN A  25       3.163  -2.986   9.712  1.00 89.88           O  
ATOM    203  N   GLN A  26      -1.662  -0.181   9.970  1.00 89.17           N  
ATOM    204  CA  GLN A  26      -3.096  -0.412   9.833  1.00 89.17           C  
ATOM    205  C   GLN A  26      -3.848   0.899   9.620  1.00 89.17           C  
ATOM    206  CB  GLN A  26      -3.644  -1.138  11.063  1.00 89.17           C  
ATOM    207  O   GLN A  26      -4.818   0.948   8.862  1.00 89.17           O  
ATOM    208  CG  GLN A  26      -3.100  -2.550  11.236  1.00 89.17           C  
ATOM    209  CD  GLN A  26      -3.752  -3.292  12.388  1.00 89.17           C  
ATOM    210  NE2 GLN A  26      -3.710  -4.619  12.337  1.00 89.17           N  
ATOM    211  OE1 GLN A  26      -4.289  -2.678  13.315  1.00 89.17           O  
ATOM    212  N   ASN A  27      -3.386   1.918  10.410  1.00 87.64           N  
ATOM    213  CA  ASN A  27      -3.999   3.230  10.229  1.00 87.64           C  
ATOM    214  C   ASN A  27      -3.761   3.770   8.821  1.00 87.64           C  
ATOM    215  CB  ASN A  27      -3.472   4.217  11.272  1.00 87.64           C  
ATOM    216  O   ASN A  27      -4.645   4.397   8.235  1.00 87.64           O  
ATOM    217  CG  ASN A  27      -4.315   5.474  11.365  1.00 87.64           C  
ATOM    218  ND2 ASN A  27      -3.661   6.630  11.330  1.00 87.64           N  
ATOM    219  OD1 ASN A  27      -5.542   5.407  11.467  1.00 87.64           O  
ATOM    220  N   LEU A  28      -2.573   3.598   8.353  1.00 84.92           N  
ATOM    221  CA  LEU A  28      -2.270   4.053   7.000  1.00 84.92           C  
ATOM    222  C   LEU A  28      -3.074   3.267   5.970  1.00 84.92           C  
ATOM    223  CB  LEU A  28      -0.773   3.913   6.711  1.00 84.92           C  
ATOM    224  O   LEU A  28      -3.522   3.828   4.967  1.00 84.92           O  
ATOM    225  CG  LEU A  28       0.147   4.926   7.396  1.00 84.92           C  
ATOM    226  CD1 LEU A  28       1.608   4.543   7.182  1.00 84.92           C  
ATOM    227  CD2 LEU A  28      -0.124   6.333   6.875  1.00 84.92           C  
ATOM    228  N   LYS A  29      -3.145   1.945   6.301  1.00 81.87           N  
ATOM    229  CA  LYS A  29      -3.961   1.116   5.419  1.00 81.87           C  
ATOM    230  C   LYS A  29      -5.431   1.521   5.487  1.00 81.87           C  
ATOM    231  CB  LYS A  29      -3.807  -0.363   5.778  1.00 81.87           C  
ATOM    232  O   LYS A  29      -6.136   1.490   4.477  1.00 81.87           O  
ATOM    233  CG  LYS A  29      -2.443  -0.944   5.438  1.00 81.87           C  
ATOM    234  CD  LYS A  29      -2.375  -2.433   5.753  1.00 81.87           C  
ATOM    235  CE  LYS A  29      -1.009  -3.015   5.415  1.00 81.87           C  
ATOM    236  NZ  LYS A  29      -0.950  -4.482   5.685  1.00 81.87           N  
ATOM    237  N   LYS A  30      -5.765   1.874   6.607  1.00 85.09           N  
ATOM    238  CA  LYS A  30      -7.161   2.270   6.771  1.00 85.09           C  
ATOM    239  C   LYS A  30      -7.409   3.661   6.195  1.00 85.09           C  
ATOM    240  CB  LYS A  30      -7.558   2.236   8.248  1.00 85.09           C  
ATOM    241  O   LYS A  30      -8.480   3.929   5.646  1.00 85.09           O  
ATOM    242  CG  LYS A  30      -7.697   0.832   8.819  1.00 85.09           C  
ATOM    243  CD  LYS A  30      -8.197   0.861  10.257  1.00 85.09           C  
ATOM    244  CE  LYS A  30      -8.315  -0.542  10.837  1.00 85.09           C  
ATOM    245  NZ  LYS A  30      -8.805  -0.519  12.248  1.00 85.09           N  
ATOM    246  N   GLU A  31      -6.309   4.489   6.498  1.00 82.01           N  
ATOM    247  CA  GLU A  31      -6.463   5.862   6.025  1.00 82.01           C  
ATOM    248  C   GLU A  31      -6.529   5.916   4.501  1.00 82.01           C  
ATOM    249  CB  GLU A  31      -5.315   6.737   6.533  1.00 82.01           C  
ATOM    250  O   GLU A  31      -7.296   6.698   3.936  1.00 82.01           O  
ATOM    251  CG  GLU A  31      -5.551   8.229   6.349  1.00 82.01           C  
ATOM    252  CD  GLU A  31      -4.418   9.087   6.888  1.00 82.01           C  
ATOM    253  OE1 GLU A  31      -4.054  10.092   6.236  1.00 82.01           O  
ATOM    254  OE2 GLU A  31      -3.889   8.752   7.971  1.00 82.01           O  
ATOM    255  N   LYS A  32      -5.936   4.831   3.844  1.00 68.62           N  
ATOM    256  CA  LYS A  32      -5.962   4.836   2.384  1.00 68.62           C  
ATOM    257  C   LYS A  32      -7.102   3.972   1.852  1.00 68.62           C  
ATOM    258  CB  LYS A  32      -4.627   4.347   1.822  1.00 68.62           C  
ATOM    259  O   LYS A  32      -7.366   3.956   0.648  1.00 68.62           O  
ATOM    260  CG  LYS A  32      -4.017   5.275   0.781  1.00 68.62           C  
ATOM    261  CD  LYS A  32      -2.506   5.100   0.694  1.00 68.62           C  
ATOM    262  CE  LYS A  32      -1.906   5.958  -0.412  1.00 68.62           C  
ATOM    263  NZ  LYS A  32      -0.427   5.779  -0.511  1.00 68.62           N  
ATOM    264  N   GLY A  33      -8.289   3.732   2.658  1.00 66.72           N  
ATOM    265  CA  GLY A  33      -9.574   3.249   2.178  1.00 66.72           C  
ATOM    266  C   GLY A  33      -9.494   2.603   0.807  1.00 66.72           C  
ATOM    267  O   GLY A  33     -10.447   2.667   0.028  1.00 66.72           O  
ATOM    268  N   LEU A  34      -8.497   1.742   0.370  1.00 59.28           N  
ATOM    269  CA  LEU A  34      -8.790   0.893  -0.780  1.00 59.28           C  
ATOM    270  C   LEU A  34      -7.906  -0.349  -0.778  1.00 59.28           C  
ATOM    271  CB  LEU A  34      -8.594   1.671  -2.084  1.00 59.28           C  
ATOM    272  O   LEU A  34      -6.677  -0.242  -0.796  1.00 59.28           O  
ATOM    273  CG  LEU A  34      -9.830   1.828  -2.972  1.00 59.28           C  
ATOM    274  CD1 LEU A  34     -10.458   3.203  -2.769  1.00 59.28           C  
ATOM    275  CD2 LEU A  34      -9.467   1.611  -4.437  1.00 59.28           C  
ATOM    276  N   PHE A  35      -8.021  -1.203   0.321  1.00 59.99           N  
ATOM    277  CA  PHE A  35      -7.748  -2.600   0.006  1.00 59.99           C  
ATOM    278  C   PHE A  35      -7.160  -2.735  -1.394  1.00 59.99           C  
ATOM    279  CB  PHE A  35      -9.026  -3.438   0.122  1.00 59.99           C  
ATOM    280  O   PHE A  35      -7.729  -2.228  -2.363  1.00 59.99           O  
ATOM    281  CG  PHE A  35      -9.664  -3.386   1.483  1.00 59.99           C  
ATOM    282  CD1 PHE A  35      -9.197  -4.190   2.516  1.00 59.99           C  
ATOM    283  CD2 PHE A  35     -10.732  -2.533   1.731  1.00 59.99           C  
ATOM    284  CE1 PHE A  35      -9.786  -4.144   3.778  1.00 59.99           C  
ATOM    285  CE2 PHE A  35     -11.326  -2.482   2.989  1.00 59.99           C  
ATOM    286  CZ  PHE A  35     -10.852  -3.289   4.010  1.00 59.99           C  
TER     287      PHE A  35                                                      
ENDMDL                                                                          
END                                                                             
`;

export const OPENFOLD2_EXAMPLE: PlaygroundResult = {
  type: 'structure',
  raw: { note: 'Example response (pre-computed)' },
  items: [
    {
      label: 'Predicted Structure (pLDDT: 86.8)',
      value: OPENFOLD2_STRUCTURE,
      format: 'structure',
      downloadFilename: 'openfold2_prediction.cif',
    },
  ],
};

// ============================================================================
// MolMIM Example
// ============================================================================
// Generated from MolMIM API using Ibuprofen (CC(C)Cc1ccc(cc1)C(C)C(=O)O) as reference
// algorithm: "none", property_name: "QED", scaled_radius: 1.0

const MOLMIM_RAW = {
  generated: [
    { smiles: 'c1noc(CCCCNCCCCCCN2CCCCC2)n1', score: 0.6015 },
    { smiles: 'c1nonc1CNCCCCCCCCCNCC[C@@H]1CCOC1', score: 0.4792 },
    { smiles: 'NCCCCCCCCCCCCCCCCO', score: 0.4271 },
    { smiles: 'NCCCCCCCCCCCCCCCCCO', score: 0.3965 },
    { smiles: 'OCCCCCCCCCCCCCCCCCO', score: 0.3602 },
    { smiles: 'OCCCCCCCCCCCCCCNCC1CCCCCC1', score: 0.2583 },
    { smiles: 'OCCCCCCCCN[C@@H]1CCCN(C(=O)CCCCCCCCCCCC2CC2)C1', score: 0.1937 },
    { smiles: 'OCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCOCCOCCOCCOCCOCCOCCOCCOCCOCCOCC', score: 0.0589 },
    { smiles: 'NCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC1', score: 0.0 },
    { smiles: 'OCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC1', score: 0.0 },
  ],
};

export const MOLMIM_EXAMPLE: PlaygroundResult = {
  type: 'molecules',
  raw: MOLMIM_RAW,
  items: [
    {
      label: `Generated Analogs (${MOLMIM_RAW.generated.length})`,
      value: MOLMIM_RAW.generated
        .map(
          (m, i) => `${i + 1}. ${m.smiles}${m.score ? ` (score: ${m.score.toFixed(3)})` : ''}`
        )
        .join('\n'),
      format: 'smiles' as const,
      downloadFilename: 'molmim_molecules.txt',
    },
  ],
};

// ============================================================================
// GenMol Example
// ============================================================================
// Generated from GenMol API using de novo generation: [*{20-30}]
// temperature: 2.0, scoring: QED, unique: true

const GENMOL_RAW = {
  status: 'success',
  molecules: [
    { smiles: 'Cc1cc(-c2ccncc2)nc(C)n1', score: 0.683 },
    { smiles: 'CSCc1ccccc1', score: 0.605 },
    { smiles: 'CC(N)C1(CC(=O)NCCS)CCC1', score: 0.599 },
    { smiles: 'CO[C@H]1CCNC1', score: 0.501 },
    { smiles: 'Cc1cccc(N)c1', score: 0.500 },
    { smiles: 'CCC#Cc1ccccn1', score: 0.489 },
    { smiles: 'N=C(O)Nc1ncc(N)nc1Br', score: 0.421 },
    { smiles: 'O=[N+]([O-])CC1COC1', score: 0.375 },
    { smiles: 'CCC[N+](=O)[O-]', score: 0.368 },
  ],
};

export const GENMOL_EXAMPLE: PlaygroundResult = {
  type: 'molecules',
  raw: GENMOL_RAW,
  items: [
    {
      label: `Generated Molecules (${GENMOL_RAW.molecules.length})`,
      value: GENMOL_RAW.molecules
        .map(
          (m, i) => `${i + 1}. ${m.smiles}${m.score ? ` (score: ${m.score.toFixed(3)})` : ''}`
        )
        .join('\n'),
      format: 'smiles' as const,
      downloadFilename: 'genmol_molecules.txt',
    },
  ],
};

// ============================================================================
// DiffDock Example
// ============================================================================
// Generated from DiffDock API docking Ibuprofen (CC(C)Cc1ccc(cc1)C(C)C(=O)O)
// against HP35 villin headpiece (LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF)
// num_poses: 5, time_divisions: 20, steps: 18

const DIFFDOCK_POSE_0 = `protein_ligand
     RDKit          3D

 15 15  0  0  0  0  0  0  0  0999 V2000
   -4.1806   -2.5772    5.7127 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.5513   -1.4114    4.9799 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.7559   -0.5943    5.9247 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.7947   -1.9145    3.7877 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.1630   -0.8590    2.9866 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.7045    0.3993    2.9370 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.1279    1.4207    2.1859 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.9640    1.1516    1.4634 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.4269   -0.1086    1.5167 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.0226   -1.0975    2.2701 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.3168    2.2147    0.6488 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.9097    2.7288    1.3335 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.0462    1.7308   -0.7291 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.6285    0.7250   -1.2135 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.8672    2.3842   -1.5267 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
  2  4  1  0
  4  5  1  0
  5  6  2  0
  6  7  1  0
  7  8  2  0
  8  9  1  0
  9 10  2  0
  8 11  1  0
 11 12  1  0
 11 13  1  0
 13 14  2  0
 13 15  1  0
 10  5  1  0
M  END
$$$$
`;

const DIFFDOCK_POSE_1 = `protein_ligand
     RDKit          3D

 15 15  0  0  0  0  0  0  0  0999 V2000
   -2.4318   -0.4303    4.4820 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.6667   -1.1065    5.0388 C   0  0  0  0  0  0  0  0  0  0  0  0
   -4.5072   -0.1138    5.7466 C   0  0  0  0  0  0  0  0  0  0  0  0
   -4.3638   -1.8610    3.9472 C   0  0  0  0  0  0  0  0  0  0  0  0
   -5.6241   -2.4901    4.3604 C   0  0  0  0  0  0  0  0  0  0  0  0
   -5.7121   -3.1615    5.5523 C   0  0  0  0  0  0  0  0  0  0  0  0
   -6.8938   -3.7682    5.9710 C   0  0  0  0  0  0  0  0  0  0  0  0
   -8.0202   -3.6882    5.1500 C   0  0  0  0  0  0  0  0  0  0  0  0
   -7.9263   -3.0155    3.9592 C   0  0  0  0  0  0  0  0  0  0  0  0
   -6.7413   -2.4259    3.5741 C   0  0  0  0  0  0  0  0  0  0  0  0
   -9.3016   -4.3226    5.5604 C   0  0  0  0  0  0  0  0  0  0  0  0
  -10.0796   -4.7608    4.3603 C   0  0  0  0  0  0  0  0  0  0  0  0
   -9.0576   -5.4275    6.5225 C   0  0  0  0  0  0  0  0  0  0  0  0
   -9.6354   -6.5419    6.4252 O   0  0  0  0  0  0  0  0  0  0  0  0
   -8.1749   -5.2559    7.5661 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
  2  4  1  0
  4  5  1  0
  5  6  2  0
  6  7  1  0
  7  8  2  0
  8  9  1  0
  9 10  2  0
  8 11  1  0
 11 12  1  0
 11 13  1  0
 13 14  2  0
 13 15  1  0
 10  5  1  0
M  END
$$$$
`;

const DIFFDOCK_POSE_2 = `protein_ligand
     RDKit          3D

 15 15  0  0  0  0  0  0  0  0999 V2000
   -2.3393   -2.3647    2.6961 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.7536   -0.9419    3.0057 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.8432    0.0064    2.3238 C   0  0  0  0  0  0  0  0  0  0  0  0
   -4.2075   -0.7600    2.6897 C   0  0  0  0  0  0  0  0  0  0  0  0
   -5.1032   -1.6412    3.4487 C   0  0  0  0  0  0  0  0  0  0  0  0
   -4.6071   -2.4769    4.4154 C   0  0  0  0  0  0  0  0  0  0  0  0
   -5.4319   -3.3240    5.1516 C   0  0  0  0  0  0  0  0  0  0  0  0
   -6.8042   -3.3192    4.8948 C   0  0  0  0  0  0  0  0  0  0  0  0
   -7.2948   -2.4813    3.9269 C   0  0  0  0  0  0  0  0  0  0  0  0
   -6.4509   -1.6550    3.2160 C   0  0  0  0  0  0  0  0  0  0  0  0
   -7.7196   -4.2087    5.6588 C   0  0  0  0  0  0  0  0  0  0  0  0
   -8.7934   -3.4097    6.3266 C   0  0  0  0  0  0  0  0  0  0  0  0
   -8.2598   -5.2825    4.7864 C   0  0  0  0  0  0  0  0  0  0  0  0
   -9.0467   -6.1655    5.2181 O   0  0  0  0  0  0  0  0  0  0  0  0
   -7.9056   -5.3392    3.4564 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
  2  4  1  0
  4  5  1  0
  5  6  2  0
  6  7  1  0
  7  8  2  0
  8  9  1  0
  9 10  2  0
  8 11  1  0
 11 12  1  0
 11 13  1  0
 13 14  2  0
 13 15  1  0
 10  5  1  0
M  END
$$$$
`;

const DIFFDOCK_POSE_3 = `protein_ligand
     RDKit          3D

 15 15  0  0  0  0  0  0  0  0999 V2000
   -2.1245   -1.3688    2.6871 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.3157   -0.5037    2.3344 C   0  0  0  0  0  0  0  0  0  0  0  0
   -4.4562   -0.8337    3.2195 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.9097    0.9392    2.3382 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.7705    1.2462    1.4648 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.9538    1.4437    0.1207 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.8927    1.7362   -0.7326 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.3945    1.8305   -0.2001 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.5717    1.6321    1.1448 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.5002    1.3440    1.9622 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5549    2.1410   -1.0774 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4088    1.4628   -2.4026 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.7439    3.6091   -1.2003 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.6834    4.3790   -0.2059 O   0  0  0  0  0  0  0  0  0  0  0  0
    1.9952    4.1753   -2.4306 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
  2  4  1  0
  4  5  1  0
  5  6  2  0
  6  7  1  0
  7  8  2  0
  8  9  1  0
  9 10  2  0
  8 11  1  0
 11 12  1  0
 11 13  1  0
 13 14  2  0
 13 15  1  0
 10  5  1  0
M  END
$$$$
`;

const DIFFDOCK_POSE_4 = `protein_ligand
     RDKit          3D

 15 15  0  0  0  0  0  0  0  0999 V2000
   -2.5130    3.4265    0.4952 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.1828    2.3722   -0.5398 C   0  0  0  0  0  0  0  0  0  0  0  0
   -0.8615    1.7729   -0.2429 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.3129    1.3924   -0.6398 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.2578    0.3074    0.3473 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.8036    0.4688    1.5944 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.7667   -0.5422    2.5516 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.1550   -1.7548    2.2281 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.6109   -1.9106    0.9794 C   0  0  0  0  0  0  0  0  0  0  0  0
   -2.6643   -0.8896    0.0547 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.0943   -2.8600    3.2219 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.6209   -2.4059    4.5462 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.7907   -4.0676    2.7093 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.9785   -4.2628    1.4797 O   0  0  0  0  0  0  0  0  0  0  0  0
   -4.2576   -5.0229    3.5851 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
  2  4  1  0
  4  5  1  0
  5  6  2  0
  6  7  1  0
  7  8  2  0
  8  9  1  0
  9 10  2  0
  8 11  1  0
 11 12  1  0
 11 13  1  0
 13 14  2  0
 13 15  1  0
 10  5  1  0
M  END
$$$$
`;

const DIFFDOCK_RAW = {
  ligand_positions: [DIFFDOCK_POSE_0, DIFFDOCK_POSE_1, DIFFDOCK_POSE_2, DIFFDOCK_POSE_3, DIFFDOCK_POSE_4],
  position_confidence: [-1.7879, -2.5771, -2.7596, -3.1826, -3.7566],
  status: 'success',
  details: '',
};

// Confidence: exp(rawScore) → [16.7%, 7.6%, 6.3%, 4.1%, 2.3%]
const DIFFDOCK_POSES = [
  { sdf: DIFFDOCK_POSE_0, confidence: 0.1673 },
  { sdf: DIFFDOCK_POSE_1, confidence: 0.0760 },
  { sdf: DIFFDOCK_POSE_2, confidence: 0.0633 },
  { sdf: DIFFDOCK_POSE_3, confidence: 0.0415 },
  { sdf: DIFFDOCK_POSE_4, confidence: 0.0234 },
];

export const DIFFDOCK_EXAMPLE: PlaygroundResult = {
  type: 'docking',
  raw: DIFFDOCK_RAW,
  proteinStructure: OPENFOLD3_STRUCTURE,
  items: DIFFDOCK_POSES.map((pose, i) => ({
    label: `Pose ${i + 1} — ${(pose.confidence * 100).toFixed(1)}% confidence`,
    value: pose.sdf,
    format: 'docking' as const,
    downloadFilename: `diffdock_pose_${i + 1}.sdf`,
  })),
};

// ============================================================================
// MSA Search Example
// ============================================================================
// Generated from MSA Search API using HP35 villin headpiece
// databases: Uniref30_2302, colabfold_envdb_202108
// Shows first 20 of 202 sequences found

const MSA_ALIGNMENT = `>A|-|A
LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
>UniRef100_UPI00020DB0F1\t62\t1.00\t1.345E-09\t0\t34\t35\t32\t66\t67
LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
>UniRef100_UPI00005B2DE6\t62\t1.00\t1.345E-09\t0\t34\t35\t32\t66\t67
LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
>UniRef100_UPI0001815F8B\t62\t1.00\t1.345E-09\t0\t34\t35\t32\t66\t67
LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
>UniRef100_UPI0021E349EE\t62\t1.00\t1.345E-09\t0\t34\t35\t81\t115\t229
LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
>UniRef100_UPI0021E349E0\t62\t1.00\t1.345E-09\t0\t34\t35\t81\t115\t273
LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
>UniRef100_A0A8B9R3J0\t60\t0.857\t6.619E-09\t0\t34\t35\t49\t83\t84
LSDQDFQAVFGMNRSAFGNLPVWKQQNLKKEKGLF
>UniRef100_A0A493SVS3\t60\t0.857\t6.619E-09\t0\t34\t35\t334\t368\t369
LSDQDFQAVFGMNRSAFGNLPVWKQQNLKKEKGLF
>UniRef100_A0A3Q2G8Z3\t59\t0.714\t1.252E-08\t0\t34\t35\t775\t809\t810
LSDDDFSSVFSMTKDEFAGLPQWKQLNLKKEKGLF
>UniRef100_UPI0018E28CDE\t59\t0.714\t1.252E-08\t0\t34\t35\t781\t815\t816
LSDDDFSSVFSMTKDEFAGLPQWKQLNLKKEKGLF
>UniRef100_A0A3Q2C8C0\t59\t0.714\t1.252E-08\t0\t34\t35\t781\t815\t816
LSDDDFSSVFSMTKDEFAGLPQWKQLNLKKEKGLF
>UniRef100_UPI00020F052F\t59\t0.971\t1.723E-08\t0\t34\t35\t32\t66\t67
LSDEDFKAVFGMTRSAFANGPLWKQQNLKKEKGLF
>UniRef100_UPI000529D929\t59\t0.800\t1.723E-08\t0\t34\t35\t287\t321\t322
LSDQDFQAVFGMKRSEFGNLPLWKQQKLKKDKGLF
>UniRef100_UPI0015ABF9A0\t58\t0.657\t2.370E-08\t0\t34\t35\t784\t818\t819
LSDEDFCDVFGITKDEFFSLPQWKQLNMKKSKGLF
>UniRef100_UPI00020DB0F2\t57\t0.916\t4.485E-08\t0\t34\t35\t32\t67\t68
LSDEDFKAVFGMTRSAFaNGLPLWKQQNLKKEKGLF
>UniRef100_UPI00005B2DE5\t57\t0.971\t6.169E-08\t0\t34\t35\t32\t66\t67
LSDEDFKAVFGMTRSAFANLPLYKQQNLKKEKGLF
>UniRef100_A0A674I416\t57\t0.771\t6.169E-08\t0\t34\t35\t50\t84\t85
LSSDDFTVVFGMPRNAFAALPLWKQQKLKKEKGLF
>UniRef100_UPI001FAC87B1\t57\t0.657\t6.169E-08\t0\t34\t35\t781\t815\t816
LSDADFSSLFGMTKDNFASLPQWKQLNLKKKTGLF
>UniRef100_UPI00165CA5C3\t57\t0.657\t6.169E-08\t0\t34\t35\t781\t815\t816
LSDADFSSLFGMTKDDFTSLPQWRQLNLKKEKGLF
>UniRef100_A0A3Q2P4M0\t57\t0.657\t6.169E-08\t0\t34\t35\t783\t817\t818
LSDADFSSLFGMTKDDFTSLPQWRQLNLKKEKGLF`;

export const MSA_SEARCH_EXAMPLE: PlaygroundResult = {
  type: 'alignment',
  raw: { metrics: { search_type: 'colabfold' }, alignments: { colabfold: { a3m: { alignment: MSA_ALIGNMENT } } } },
  items: [
    {
      label: `MSA Alignment (${(MSA_ALIGNMENT.match(/>/g) || []).length} sequences)`,
      value: MSA_ALIGNMENT,
      format: 'code',
      downloadFilename: 'msa_search_result.a3m',
    },
  ],
};

// ============================================================================
// Evo2 Example
// ============================================================================
// Generated from Evo2-40B API with seed sequence ATCGATCGATCGATCG
// num_tokens: 100, temperature: 1.0, top_k: 4

const EVO2_SEQUENCE = 'ATCGATCGATCGTTTGCGATGGACCTATTGATCGAATAGTGTGTATGCTGTTGTTCCGTATAGTTTTGCTGGACAACGGTCACGAAACGCGTGCACGTCC';

export const EVO2_EXAMPLE: PlaygroundResult = {
  type: 'sequences',
  raw: { sequence: EVO2_SEQUENCE, elapsed_ms: 4107 },
  items: [
    {
      label: `Generated Sequence (${EVO2_SEQUENCE.length} nt)`,
      value: EVO2_SEQUENCE,
      format: 'sequence',
      downloadFilename: 'evo2_generated.fasta',
    },
  ],
};

// ============================================================================
// ProteinMPNN Example
// ============================================================================
// Generated from ProteinMPNN API using HP35 villin headpiece backbone
// sampling_temp: 0.1, num_seq_per_target: 8, chains: A

const PROTEINMPNN_MFASTA = `>input, score=2.3144, global_score=2.3144, fixed_chains=[], designed_chains=['A'], model_name=v_48_002, seed=102
LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF
>T=0.1, sample=1, score=1.1805, global_score=1.1805, seq_recovery=0.2286
MTAEDVEKLAAAANEEFLKLPEEERKRIETELGLV
>T=0.1, sample=2, score=1.1520, global_score=1.1520, seq_recovery=0.3143
MTEEDLKEIGEKLRKEFEKLPEEEQKRILKELGIV
>T=0.1, sample=3, score=1.1972, global_score=1.1972, seq_recovery=0.2286
MTAEDVLEIATKLNEEFEKLPEEERKRIETELGLV
>T=0.1, sample=4, score=1.2138, global_score=1.2138, seq_recovery=0.2286
MTEEDLKRIGEAANKEFLKKSKEEQERIMTELGLI
>T=0.1, sample=5, score=1.1671, global_score=1.1671, seq_recovery=0.2857
MTEEDVKEIGAALNKEFEKLPKEEQERILTELGLV
>T=0.1, sample=6, score=1.2156, global_score=1.2156, seq_recovery=0.2571
MTAEDVRELAAAANKEFQKLPKEEQERIATELGLV
>T=0.1, sample=7, score=1.1546, global_score=1.1546, seq_recovery=0.2857
MTAEDLKKIGKKLSKEFKKLSKEEQEKIEKELGLI
>T=0.1, sample=8, score=1.1922, global_score=1.1922, seq_recovery=0.2000
MTEEDIKVISDKLNKEFLKLSEEERKRIETELGII`;

export const PROTEINMPNN_EXAMPLE: PlaygroundResult = {
  type: 'sequences',
  raw: {
    mfasta: PROTEINMPNN_MFASTA,
    scores: [1.1805, 1.1520, 1.1972, 1.2138, 1.1671, 1.2156, 1.1546, 1.1922],
  },
  items: [
    {
      label: 'Designed Sequences (8)',
      value: PROTEINMPNN_MFASTA,
      format: 'sequence',
      downloadFilename: 'proteinmpnn_sequences.fasta',
    },
  ],
};
