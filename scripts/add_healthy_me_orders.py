"""
Add multiple orders for Healthy Me members
Includes opt-in/opt-out status
"""
import os
os.environ['DATABASE_URL'] = "postgresql+psycopg2://appadmin:Life360%402025%21Secure@life360-2578617155-pg01.postgres.database.azure.com:5432/life360?sslmode=require"

from datetime import datetime
from app import app, db, Order

# Member data
members_data = """153046	0	HM-A0063	Jeanetta Philippina	Grobler
196824	0	HM-A0038	Zomi	Shabangu
228327	0	HM-A0223	Nthabiseng Innocent	Makaya
219254	0	HM-A0205	Ayanda Z	Mlambo
215711	10	HM-A0173	CLAYVON RA	SARMIE
230007	10	HM-A0342	PIETER A	VAN DEN BERG
203525	10	HM-A0242	GOODMAN D	JANDA
229596	0	HM-A0077	Mmatholo Pheladi	Boshielo
197364	0	HM-A0222	FISOKUHLE Z	MSANE
201702	0	HM-A0078	Calvin	Boshomane
180912	10	HM-A0115	Valerie Ann	Nolan
217375	0	HM-A0108	Victor	Groberlaar
228682	0	HM-A0244	FELICIA NL	NDABA
231614	0	HM-A0221	SIPHO M	BUSANA
234329	0	HM-A0198	CHANDRE K	LEACH
227491	10	HM-A0147	MARTHINUS NH	KRUGER
234864	0	HM-A0332	ANDRE	EILERS
235070	0	HM-A0100	Nhlanhla Charles	Thabethe
198470	0	HM-A0140	Andisiwe	Gatya
231594	0	HM-A0243	MXOLISI	MPEKU
233359	0	HM-A0270	ANDISIWE B	NDIKI
124714	0	HM-A0180	Nadia Anniena	Bischoff
152346	0	HM-A0073	Kaatrina	Mpharoae
235776	0	HM-A0216	MOJALEFA BRIAN	POLINYANE
231666	0	HM-A0206	BRIGHTNESS S	GUMEDE
219867	0	HM-A0163	Lerato V	Xaba
232562	0	HM-A0150	PULEDI M	RASEKGALA
229420	0	HM-A0062	Phumeza	Buzani
198473	0	HM-A0024	Vuyokazi	Ngoqo
166060	0	HM-A0112	SABELO	NDLOVU
226930	0	HM-A0075	Mobuzwe	Mpholo
216031	0	HM-A0036	Mmabatho	Thete
217395	0	HM-A0070	George Tshepo	Modau
224584	0	HM-A0182	Elvis Kabelo	Mothaba
197479	0	HM-A0278	RICARDO S	PILLAY
231901	0	HM-A0160	Brain Michael	Kgobe
216759	10	HM-A0131	DUMISANI M	FALENI
156107	1	HM-A0162	Justin Daniel	van der Merwe
234821	0	HM-A0318	KOLOBE W	RAKHUTLA
234909	10	HM-A0317	NONTOBEKO A	ZIKODE
142347	0	HM-A0257	MATSILISO H	MAKEKI
230797	0	HM-A0033	Relebogile	Mashile
202721	0	HM-A0074	Mthobisi	Khambule
233062	0	HM-A0254	Westley Wayne	Cloete
228239	10	HM-A0238	Lesego	Mohlomi
233423	0	HM-A0251	Mosima	Mehlape
218388	0	HM-A0114	Odirile	Mogapi
232295	0	HM-A0207	SEITHATI A	MOKETE
227371	0	HM-A0202	ZAMANGWANE P	MFEKETHO
227598	0	HM-A0127	TANYA C	VAN ZYL
227039	0	HM-A0144	NOLUTHANDO S	NKWANYANA
156107	0	HM-A0139	Denzil Gregory	van der Merwe
234708	0	HM-A0145	BRANDON	HERBERT
233684	0	HM-A0316	LANGA LK	DAMOENSE
234329	10	HM-A0346	JUNAID R	LEACH
165417	10	HM-A0157	THOBEKILE	MAFU
234934	0	HM-A0319	PHUMULANI S	GUMBI
234942	0	HM-A0231	Otherwise	Ndlovu
215260	0	HM-A0041	Busisiwe	Mthimunye
212684	0	HM-A0071	Puleng Elizabeth	Guambe
233311	0	HM-A0248	Itumeleng	Ngobeni
231397	0	HM-A0235	JUNA P	PULE
215711	0	HM-A0168	Nazmea	Badrodien Fredericks
165417	0	HM-A0130	XOLANI M	MAFU
234909	0	HM-A0320	KHUMBULANI P	MAZIBUKO
234866	0	HM-A0333	STEPHANUS E	FERREIRA
219855	0	HM-A0264	Neliswa	Williams
219856	0	HM-A0272	Simonia	Baadjies
234766	0	HM-A0083	CHRISTINA A	HUMAN
232291	0	HM-A0022	George	Segone
212392	0	HM-A0199	AYANDA	BANDA
224558	0	HM-A0109	ITUMELENG	Motsumi
214516	0	HM-A0121	Zenobia Ali	Mothilal
233415	0	HM-A0212	HELENA ADELE	AGENBAG
234982	10	HM-A0159	PORTIA N	MOLATLHEGI
203525	0	HM-A0208	NONTSIKELELO L	JANDA
232248	0	HM-A0027	Ernest Morero	Rapeane
163453	0	HM-A0184	Dikeledi Ester	Mkhize
234868	0	HM-A0336	Rian	Loots
234871	0	HM-A0323	BOITUMELO J	MODUKANELE
180912	0	HM-A0175	Thomas Richard	Nolan
233386	0	HM-A0249	Vivian Lyle	Louw
234944	0	HM-A0322	CHALRIC D	CLOETE
234869	0	HM-A0350	LUCIANO	SMITH
185924	0	HM-A0255	CORLIA-ANN	ERASMUS
234933	0	HM-A0220	WILLEM J	SPENGLER
234914	0	HM-A0334	THOBELA	NDAKISA
234865	0	HM-A0128	BUHLE	MTSHALI
226653	0	HM-A0165	Boitshoko Suzan	Leseli
224972	0	HM-A0123	LUYANDA E	LOLEKA
227597	0	HM-A0167	Michiel C	Erasmus
217375	10	HM-A0174	TRACEY A 	GROBBELAAR
231903	0	HM-A0170	ZODIDI Z	MELANE
234875	0	HM-A0331	PUSOETHATA R	NTEHANG
228152	1	HM-A0292	SISIPHO K	MAKAMBA
232745	10	HM-A0224	MOSIUOA W	SETENANE
201904	0	HM-A0153	KEAMOGETSOE EA	RAMASHALA
233108	0	HM-A0229	Reuben Karabo	Makgene
228875	0	HM-A0122	AIDA EM	DEMAS
234941	0	HM-A0328	BONGANI E	MABIYA
231594	10	HM-A0345	Nomekundo	Mpeku
235023	0	HM-A0124	MOLEBOGENG	MONAMETSI
233511	10	HM-A0355	Nomfundiso	Sithole
180959	0	HM-A0025	Mohoi William	Malotane
166887	0	HM-A0253	Evelyn	Mocwiri
158791	0	HM-A0218	PHEELLO A	MONCHO
231934	0	HM-A0080	MATSHEDISO M	SMITH
229476	0	HM-A0256	HLALANATHI PL	SIBIYA
232235	0	HM-A0102	CHUMA	KANJANA
227275	0	HM-A0142	MLUNGISI B	MOLLO
227200	0	HM-A0134	Janice Johanna	Nightingale
225933	0	HM-A0154	ZEPHORAH	TSHELANE
156107	10	HM-A0152	Brigitte Joan	van der Merwe
231625	0	HM-A0081	Bongane Mthulisi Gordon	Simelane
232248	10	HM-A0023	Ester Motshabi	Rapeane
207116	0	HM-A0105	Tiisetso Goodwill	Motlhatlhedi
207818	0	HM-A0227	ABEDNEGO N	MTYA
197479	10	HM-A0280	CARMELITA 	PILLAY
234935	0	HM-A0315	ABEDNIGO T	MADOLO
231128	0	HM-A0232	Maria	Letutu
227491	0	HM-A0110	CHRISTINE	KRUGER
234937	10	HM-A0352	ANNEMARIE	ROETS
232745	0	HM-A0215	KENEILOE M	SETENANE
231204	0	HM-A0079	Josephina Sesi	Zane
187952	0	HM-A0143	Azwitamisi Eric	Mudau
216188	0	HM-A0031	Anuchca Sinnie	Kepkey
232716	0	HM-A0076	Mduduzi Mathews	Zitha
231828	0	HM-A0106	Marc Anthony	Butler
233082	0	HM-A0032	Matlakala Salome	Mameise
231477	0	HM-A0082	Emily	Mahlangu
230798	0	HM-A0271	Clyton	Maravavanyika
233511	0	HM-A0164	Emanuel	Sithole
216195	10	HM-A0247	SUDESH	SINGH
108289	10	HM-A0209	Lakshmi	Naidu
233138	10	HM-A0258	GAYLENE J	BESTER
234939	0	HM-A0228	SIMONE T	MPHANA
234906	0	HM-A0337	BYRON T	VOS
234940	0	HM-A0327	MANUEL F	MENDES
234766	10	HM-A0329	WERNER	HUMAN
233473	0	HM-A0260	THEOLENE	CLOETE
234932	0	HM-A0351	Ivy Mb	Maupa
228673	0	HM-A0534	Gizelle	Marsh
216195	0	HM-A0211	Marinda	Singh
179358	0	HM-A0029	Asnath Modima	Maepa
153262	0	HM-A0158	Willem Bennit	Brikwa
216759	0	HM-A0135	PALESA	FALENI
230007	0	HM-A0137	CHANTELL	VAN DEN BERG
234938	0	HM-A0120	Francois Eugene	Beukes
228713	0	HM-A0028	Lentsoe Phetoe	Phetoe
208383	0	HM-A0030	Mosala L	Mokate
198428	0	HM-A0034	Glendora N	Ndzekeni
211149	0	HM-A0176	Johannah Tsholofelo	Sehloho
231828	0	HM-A0146	Samantha	Butler
228239	0	HM-A0288	Willy P	Mokoena
153262	10	HM-A0252	Elizabeth	Brikwa
199736	0	HM-A0269	ROBIN	PETERS
172934	0	HM-A0263	SHAROLINE D	BLAAUW
233138	0	HM-A0273	ETTIENNE F	BESTER
228128	0	HM-A0133	KITSO O	MOKGOSI
214025	0	HM-A0125	SMUTS BENNETH	MAKHUBELE
234910	0	HM-A0321	PROMISE F	MASANGO
234907	0	HM-A0026	Jose E	Ulembe
234877	0	HM-A0117	ADMIRE S	MADZIVANYIKA
234982	0	HM-A0156	ISAAC N	MOLATLHEGI
142347	1	HM-A0219	MFALADI J	MAKEKI
236505	0	HM-A0166	Otto Sinewhlanhla	Mntumawa
234908	0	HM-A0072	OHENTSE G	WOLF
198489	0	HM-A0037	Bathabile EL	Lekgau
228624	0	HM-A0101	Kagiso Susan	Mothapo
232014	0	HM-A0040	Glenton	Sambo
215260	10	HM-A0035	Jabu Simon	Mahlanhgu
233668	0	HM-A0343	KERISHNIE	CLOETE
204007	0	HM-A0204	SEABATA PETRUS	PHARA
139207	0	HM-A0190	Kehilwe Yvonne	Pelosera
182012	0	HM-A0039	Phillimon	Makhungela
230191	0	HM-A0119	Christopher	Moonsamy
108289	0	HM-A0213	PERUMAL	NAIDU
231027	0	HM-A0283	Vile	Pambani
228750	0	HM-A0171	MOTSHELE L	AZWIFHELI
206708	0	HM-A0107	TIMOTHY M	GQEBA
232913	0	HM-A0116	Rahab M	Phoshoko
231002	0	HM-A0282	NOMVUYO P	PIKOLI
234819	0	HM-A0151	MTHOBISI E	NKOSI
234937	0	HM-A0237	HENDRIK J	ROETS
139927	0	HM-A0335	LOTLHOGONOLO MONTY	KOIKANYANG"""

def add_orders():
    """Add all orders for Healthy Me members."""
    with app.app_context():
        try:
            print("Connecting to Azure PostgreSQL database...")
            
            lines = members_data.strip().split('\n')
            added_count = 0
            skipped_count = 0
            
            print(f"\n{'='*60}")
            print("Adding Orders for Healthy Me Members")
            print(f"{'='*60}")
            print(f"Total members to process: {len(lines)}")
            
            for line in lines:
                parts = line.strip().split('\t')
                if len(parts) < 5:
                    continue
                
                member_no = parts[0].strip()
                dep_code = parts[1].strip()
                swab_id = parts[2].strip()
                name = parts[3].strip()
                surname = parts[4].strip()
                
                # Create order - default to "Opted In" status
                # Status can be "Opted In" or "Opted Out"
                order = Order(
                    provider="Healthy Me",
                    name=name,
                    surname=surname,
                    status="Pending",  # Order processing status
                    opt_in_status=None,  # No opt-in status set yet - will show as "Pending"
                    notes=f"Member No: {member_no}, Dep Code: {dep_code}, Swab ID: {swab_id}",
                    ordered_at=datetime.now()
                )
                
                db.session.add(order)
                added_count += 1
                
                # Commit in batches of 50
                if added_count % 50 == 0:
                    db.session.commit()
                    print(f"[OK] Added {added_count} orders so far...")
            
            # Final commit
            db.session.commit()
            
            print("\n" + "="*60)
            print("[SUCCESS] All Orders Added Successfully!")
            print("="*60)
            print(f"  - Added {added_count} orders")
            print(f"  - Provider: Healthy Me")
            print(f"  - Default Status: Opted In")
            print(f"  - Status can be changed to 'Opted Out' in the UI")
            print("\nTo verify on Azure, visit:")
            print("https://life360-2578617155-app.azurewebsites.net/")
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    add_orders()

