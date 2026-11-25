import streamlit as st
import mysql.connector
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Toko Parfum", page_icon="🧴", layout="wide")


# ---------------------------------------------------------------
# Koneksi & helper database
# ---------------------------------------------------------------
def get_conn():
    cfg = st.secrets["mysql"]
    return mysql.connector.connect(
        host=cfg.get("host", "localhost"),
        port=int(cfg.get("port", 3306)),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg.get("database", "toko_parfum"),
    )


def query(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return pd.DataFrame(rows)
    finally:
        conn.close()


def execute(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()


def next_id(cur, table, col, prefix, width):
    """Buat ID berikutnya, contoh: PJ006 -> PJ007."""
    cur.execute(
        f"SELECT {col} FROM {table} WHERE {col} LIKE %s "
        f"ORDER BY LENGTH({col}) DESC, {col} DESC LIMIT 1",
        (prefix + "%",),
    )
    row = cur.fetchone()
    n = int(row[0][len(prefix):]) + 1 if row else 1
    return f"{prefix}{n:0{width}d}"


def rupiah(x):
    return "Rp {:,.0f}".format(float(x)).replace(",", ".")


def get_stok():
    return query(
        """
        SELECT v.id_varian, p.merek, p.nama_produk, v.tipe_jual, v.volume,
               v.harga_jual, v.poin_per_item,
               COALESCE(SUM(m.jumlah), 0) AS stok
        FROM varian v
        JOIN produk p ON p.id_produk = v.id_produk
        LEFT JOIN mutasi_stok m ON m.id_varian = v.id_varian
        GROUP BY v.id_varian, p.merek, p.nama_produk, v.tipe_jual, v.volume,
                 v.harga_jual, v.poin_per_item
        ORDER BY v.id_varian
        """
    )


def label_varian(r):
    return (f"{r['id_varian']} - {r['merek']} {r['nama_produk']} "
            f"({r['tipe_jual']} {r['volume']})")


# ---------------------------------------------------------------
# Halaman: Dashboard
# ---------------------------------------------------------------
def page_dashboard():
    st.header("📊 Dashboard")
    pj = query("SELECT * FROM penjualan")
    stok = get_stok()
    member = query("SELECT COUNT(*) AS n FROM pelanggan WHERE tipe_pelanggan='member'")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Penjualan", rupiah(pj["total_nilai"].sum()) if not pj.empty else "Rp 0")
    c2.metric("Jumlah Transaksi", len(pj))
    c3.metric("Jumlah Member", int(member["n"][0]))
    c4.metric("Varian Stok ≤ 2", int((stok["stok"] <= 2).sum()))

    if not pj.empty:
        pj["tanggal"] = pd.to_datetime(pj["tanggal_waktu"]).dt.strftime("%Y-%m-%d")
        pj["total_nilai"] = pj["total_nilai"].astype(float)
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Penjualan per Hari")
            st.bar_chart(pj.groupby("tanggal")["total_nilai"].sum())
        with col_b:
            st.subheader("Penjualan per Tipe Transaksi")
            st.bar_chart(pj.groupby("tipe_transaksi")["total_nilai"].sum())

    st.subheader("Stok Saat Ini")
    tampil = stok.copy()
    tampil["harga_jual"] = tampil["harga_jual"].apply(rupiah)
    st.dataframe(tampil, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------
# Halaman: Produk & Varian
# ---------------------------------------------------------------
def page_produk():
    st.header("🧴 Produk & Varian")
    tab1, tab2, tab3 = st.tabs(["Daftar", "Tambah Produk", "Tambah Varian"])

    with tab1:
        df = get_stok()
        df["harga_jual"] = df["harga_jual"].apply(rupiah)
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab2:
        with st.form("form_produk", clear_on_submit=True):
            nama = st.text_input("Nama produk")
            merek = st.text_input("Merek")
            if st.form_submit_button("Simpan produk"):
                if not nama or not merek:
                    st.error("Nama dan merek wajib diisi.")
                else:
                    conn = get_conn()
                    try:
                        cur = conn.cursor()
                        new_id = next_id(cur, "produk", "id_produk", "PR", 2)
                        cur.execute(
                            "INSERT INTO produk VALUES (%s,%s,%s)", (new_id, nama, merek)
                        )
                        conn.commit()
                        st.success(f"Produk {new_id} tersimpan.")
                    finally:
                        conn.close()

    with tab3:
        produk = query("SELECT * FROM produk ORDER BY id_produk")
        if produk.empty:
            st.info("Tambahkan produk terlebih dahulu.")
        else:
            with st.form("form_varian", clear_on_submit=True):
                pilih = st.selectbox(
                    "Produk",
                    produk["id_produk"],
                    format_func=lambda i: "{} - {}".format(
                        produk.set_index("id_produk").loc[i, "merek"],
                        produk.set_index("id_produk").loc[i, "nama_produk"],
                    ),
                )
                tipe = st.selectbox("Tipe jual", ["decant", "BNIB"])
                volume = st.text_input("Volume (contoh: 10ml)")
                harga = st.number_input("Harga jual", min_value=0, step=10000)
                poin = st.number_input("Poin per item", min_value=0, step=1)
                if st.form_submit_button("Simpan varian"):
                    if not volume:
                        st.error("Volume wajib diisi.")
                    else:
                        conn = get_conn()
                        try:
                            cur = conn.cursor()
                            new_id = next_id(cur, "varian", "id_varian", "V", 2)
                            cur.execute(
                                "INSERT INTO varian VALUES (%s,%s,%s,%s,%s,%s)",
                                (new_id, tipe, volume, harga, poin, pilih),
                            )
                            conn.commit()
                            st.success(f"Varian {new_id} tersimpan.")
                        finally:
                            conn.close()


# ---------------------------------------------------------------
# Halaman: Transaksi Baru (kasir)
# ---------------------------------------------------------------
def page_transaksi():
    st.header("🛒 Transaksi Baru")

    if "cart" not in st.session_state:
        st.session_state.cart = []
    cart = st.session_state.cart

    kasir = query("SELECT id_kasir, nama_kasir FROM kasir WHERE is_active=1")
    pel = query("SELECT * FROM pelanggan ORDER BY id_pelanggan")
    stok = get_stok().set_index("id_varian")

    c1, c2, c3 = st.columns(3)
    id_kasir = c1.selectbox(
        "Kasir", kasir["id_kasir"],
        format_func=lambda i: kasir.set_index("id_kasir").loc[i, "nama_kasir"],
    )
    pel_idx = pel.set_index("id_pelanggan")
    id_pel = c2.selectbox(
        "Pelanggan", pel["id_pelanggan"],
        format_func=lambda i: "{} ({})".format(
            pel_idx.loc[i, "nama_pelanggan"], pel_idx.loc[i, "tipe_pelanggan"]
        ),
    )
    tipe_trx = c3.selectbox("Tipe transaksi", ["langsung", "shopee", "pre-order"])

    is_member = pel_idx.loc[id_pel, "tipe_pelanggan"] == "member"
    saldo = int(pel_idx.loc[id_pel, "saldo_poin"]) if is_member else 0
    if is_member:
        st.caption(f"Saldo poin pelanggan: **{saldo}**")

    tukar = False
    poin_dipakai = 0
    if is_member:
        tukar = st.checkbox("Tukar poin (barang gratis, tanpa pembayaran)")
        if tukar:
            poin_dipakai = st.number_input(
                "Poin yang dipakai", min_value=1, max_value=max(saldo, 1), value=min(10, max(saldo, 1))
            )

    st.subheader("Tambah barang")
    a1, a2, a3, a4 = st.columns([3, 1, 2, 1])
    id_varian = a1.selectbox(
        "Varian", stok.index,
        format_func=lambda i: "{} (stok {})".format(
            label_varian({**stok.loc[i].to_dict(), "id_varian": i}), int(stok.loc[i, "stok"])
        ),
    )
    jumlah = a2.number_input("Jumlah", min_value=1, step=1, value=1)
    harga_default = 0 if tukar else int(stok.loc[id_varian, "harga_jual"])
    harga = a3.number_input("Harga satuan", min_value=0, step=10000, value=harga_default,
                            key=f"harga_{id_varian}_{tukar}")
    a4.write("")
    a4.write("")
    if a4.button("➕ Tambah"):
        sudah = sum(x["jumlah"] for x in cart if x["id_varian"] == id_varian)
        if tipe_trx != "pre-order" and sudah + jumlah > int(stok.loc[id_varian, "stok"]):
            st.error("Stok tidak cukup.")
        else:
            for x in cart:
                if x["id_varian"] == id_varian:
                    x["jumlah"] += jumlah
                    x["harga"] = harga
                    break
            else:
                cart.append({"id_varian": id_varian, "jumlah": jumlah, "harga": harga})
            st.rerun()

    st.subheader("Keranjang")
    if not cart:
        st.info("Keranjang masih kosong.")
        return

    df = pd.DataFrame(cart)
    df["subtotal"] = df["jumlah"] * df["harga"]
    st.dataframe(df, use_container_width=True, hide_index=True)
    total = int(df["subtotal"].sum())
    st.markdown(f"### Total: {rupiah(total)}")

    if tukar:
        metode = None
        st.caption("Metode pembayaran dikosongkan karena ditukar dengan poin.")
    else:
        metode = st.selectbox("Metode pembayaran", ["QRIS", "transfer", "tunai"])

    if tipe_trx == "pre-order":
        st.warning("Pre-order: stok tidak dikurangi sekarang. Catat mutasi penjualan "
                   "di menu Mutasi Stok saat pelunasan.")

    b1, b2 = st.columns(2)
    if b2.button("🗑️ Kosongkan keranjang"):
        st.session_state.cart = []
        st.rerun()

    if b1.button("💾 Simpan transaksi", type="primary"):
        if tukar and poin_dipakai > saldo:
            st.error("Saldo poin tidak cukup.")
            return
        if tukar:
            total = 0
        conn = get_conn()
        try:
            conn.start_transaction()
            cur = conn.cursor()
            id_pj = next_id(cur, "penjualan", "id_penjualan", "PJ", 3)
            now = datetime.now().replace(microsecond=0)
            cur.execute(
                "INSERT INTO penjualan (id_penjualan, tanggal_waktu, tipe_transaksi, "
                "metode_pembayaran, id_pelanggan, id_kasir, total_nilai) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_pj, now, tipe_trx, metode, id_pel, id_kasir, total),
            )
            poin_didapat = 0
            for it in cart:
                harga_item = 0 if tukar else it["harga"]
                cur.execute(
                    "INSERT INTO detail_penjualan VALUES (%s,%s,%s,%s)",
                    (id_pj, it["id_varian"], it["jumlah"], harga_item),
                )
                poin_didapat += int(stok.loc[it["id_varian"], "poin_per_item"]) * it["jumlah"]
                if tipe_trx != "pre-order":
                    id_m = next_id(cur, "mutasi_stok", "id_mutasi", "M", 3)
                    ket = id_pj + (" (tukar poin)" if tukar else "")
                    cur.execute(
                        "INSERT INTO mutasi_stok (id_mutasi, jenis_mutasi, jumlah, "
                        "tanggal_waktu, id_varian, id_kasir, keterangan) "
                        "VALUES (%s,'penjualan',%s,%s,%s,%s,%s)",
                        (id_m, -it["jumlah"], now, it["id_varian"], id_kasir, ket),
                    )
            if is_member:
                delta = -poin_dipakai if tukar else poin_didapat
                cur.execute(
                    "UPDATE pelanggan SET saldo_poin = saldo_poin + %s WHERE id_pelanggan=%s",
                    (delta, id_pel),
                )
            conn.commit()
            st.session_state.cart = []
            st.success(f"Transaksi {id_pj} berhasil disimpan.")
        except Exception as e:
            conn.rollback()
            st.error(f"Gagal menyimpan transaksi: {e}")
        finally:
            conn.close()


# ---------------------------------------------------------------
# Halaman: Riwayat Penjualan
# ---------------------------------------------------------------
def page_riwayat():
    st.header("🧾 Riwayat Penjualan")
    df = query(
        """
        SELECT pj.id_penjualan, pj.tanggal_waktu, pj.tipe_transaksi,
               pj.metode_pembayaran, pl.nama_pelanggan, k.nama_kasir, pj.total_nilai
        FROM penjualan pj
        JOIN pelanggan pl ON pl.id_pelanggan = pj.id_pelanggan
        JOIN kasir k ON k.id_kasir = pj.id_kasir
        ORDER BY pj.tanggal_waktu DESC
        """
    )
    if df.empty:
        st.info("Belum ada transaksi.")
        return
    tipe = st.multiselect("Filter tipe transaksi", ["langsung", "shopee", "pre-order"],
                          default=["langsung", "shopee", "pre-order"])
    df = df[df["tipe_transaksi"].isin(tipe)]
    st.dataframe(df, use_container_width=True, hide_index=True)

    if not df.empty:
        pilih = st.selectbox("Lihat detail transaksi", df["id_penjualan"])
        det = query(
            """
            SELECT d.id_varian, p.merek, p.nama_produk, v.tipe_jual, v.volume,
                   d.jumlah, d.harga_satuan, d.jumlah * d.harga_satuan AS subtotal
            FROM detail_penjualan d
            JOIN varian v ON v.id_varian = d.id_varian
            JOIN produk p ON p.id_produk = v.id_produk
            WHERE d.id_penjualan = %s
            """,
            (pilih,),
        )
        st.dataframe(det, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------
# Halaman: Pelanggan
# ---------------------------------------------------------------
def page_pelanggan():
    st.header("👥 Pelanggan")
    tab1, tab2 = st.tabs(["Daftar", "Tambah Pelanggan"])
    with tab1:
        st.dataframe(query("SELECT * FROM pelanggan ORDER BY id_pelanggan"),
                     use_container_width=True, hide_index=True)
    with tab2:
        with st.form("form_pelanggan", clear_on_submit=True):
            nama = st.text_input("Nama pelanggan")
            tipe = st.selectbox("Tipe", ["member", "non-member"])
            hp = st.text_input("No HP (wajib untuk member)")
            if st.form_submit_button("Simpan"):
                if not nama:
                    st.error("Nama wajib diisi.")
                elif tipe == "member" and not hp:
                    st.error("Member wajib punya nomor HP.")
                else:
                    conn = get_conn()
                    try:
                        cur = conn.cursor()
                        new_id = next_id(cur, "pelanggan", "id_pelanggan", "PL", 2)
                        if tipe == "member":
                            cur.execute(
                                "INSERT INTO pelanggan VALUES (%s,%s,%s,'member',0)",
                                (new_id, nama, hp),
                            )
                        else:
                            cur.execute(
                                "INSERT INTO pelanggan VALUES (%s,%s,NULL,'non-member',NULL)",
                                (new_id, nama),
                            )
                        conn.commit()
                        st.success(f"Pelanggan {new_id} tersimpan.")
                    except mysql.connector.Error as e:
                        conn.rollback()
                        st.error(f"Gagal menyimpan: {e}")
                    finally:
                        conn.close()


# ---------------------------------------------------------------
# Halaman: Mutasi Stok
# ---------------------------------------------------------------
def page_mutasi():
    st.header("📦 Mutasi Stok")
    tab1, tab2 = st.tabs(["Riwayat", "Catat Mutasi"])

    with tab1:
        st.dataframe(
            query("SELECT * FROM mutasi_stok ORDER BY tanggal_waktu DESC, id_mutasi DESC"),
            use_container_width=True, hide_index=True,
        )

    with tab2:
        stok = get_stok().set_index("id_varian")
        kasir = query("SELECT id_kasir, nama_kasir FROM kasir WHERE is_active=1").set_index("id_kasir")
        with st.form("form_mutasi", clear_on_submit=True):
            id_varian = st.selectbox(
                "Varian", stok.index,
                format_func=lambda i: "{} (stok {})".format(
                    label_varian({**stok.loc[i].to_dict(), "id_varian": i}), int(stok.loc[i, "stok"])
                ),
            )
            jenis = st.selectbox(
                "Jenis mutasi",
                ["restock", "retur", "pecah", "kadaluwarsa", "tester", "penjualan"],
            )
            jumlah = st.number_input("Jumlah (angka positif)", min_value=1, step=1)
            id_kasir = st.selectbox("Dicatat oleh", kasir.index,
                                    format_func=lambda i: kasir.loc[i, "nama_kasir"])
            ket = st.text_input("Keterangan (wajib)")
            if st.form_submit_button("Simpan mutasi"):
                if not ket:
                    st.error("Keterangan wajib diisi.")
                else:
                    masuk = jenis in ("restock", "retur")
                    nilai = jumlah if masuk else -jumlah
                    if not masuk and int(stok.loc[id_varian, "stok"]) + nilai < 0:
                        st.error("Stok tidak cukup untuk mutasi ini.")
                    else:
                        conn = get_conn()
                        try:
                            cur = conn.cursor()
                            new_id = next_id(cur, "mutasi_stok", "id_mutasi", "M", 3)
                            cur.execute(
                                "INSERT INTO mutasi_stok (id_mutasi, jenis_mutasi, jumlah, "
                                "tanggal_waktu, id_varian, id_kasir, keterangan) "
                                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                (new_id, jenis, nilai,
                                 datetime.now().replace(microsecond=0),
                                 id_varian, id_kasir, ket),
                            )
                            conn.commit()
                            st.success(f"Mutasi {new_id} tersimpan.")
                        finally:
                            conn.close()


# ---------------------------------------------------------------
# Navigasi
# ---------------------------------------------------------------
PAGES = {
    "📊 Dashboard": page_dashboard,
    "🛒 Transaksi Baru": page_transaksi,
    "🧾 Riwayat Penjualan": page_riwayat,
    "🧴 Produk & Varian": page_produk,
    "👥 Pelanggan": page_pelanggan,
    "📦 Mutasi Stok": page_mutasi,
}

st.sidebar.title("Toko Parfum")
halaman = st.sidebar.radio("Menu", list(PAGES.keys()))

try:
    PAGES[halaman]()
except mysql.connector.Error as e:
    st.error(f"Tidak bisa terhubung ke database: {e}")
    st.info("Periksa file .streamlit/secrets.toml dan pastikan MySQL sedang berjalan.")
