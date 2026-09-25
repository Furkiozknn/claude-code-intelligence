# cci-adapter-ornek

Üçüncü taraf bir `cci` adaptörünün en küçük hâli. Kopyalanmak için burada, ve
CI'da gerçekten `pip install` ediliyor: `cci providers` onu listelemezse
`ci.yml` kırmızı yanar. Yani `docs/EXTENDING.md` §2b'deki talimat, çalıştığı
ölçülmeden yayımlanmış bir talimat değil.

```
uv pip install ornekler/cci-adapter-ornek
cci providers      # "ornek  ornekprov  ...  [kurulu paket]"
```

Bağlanma noktası `pyproject.toml`'daki tek satır:

```toml
[project.entry-points."cci.adapters"]
ornek = "cci_adapter_ornek:build"
```

`build(env, home)` `PROVIDERS.md` §2 arayüzünü karşılayan bir nesne döndürür.
Bu örnek hiçbir yerden veri okumaz — `capabilities().schema_verified` `false`,
çünkü doğrulanmış bir fixture'ı yok, ve `cci providers` onu bu yüzden
`DOGRULANMADI -> inferred` diye gösterir. Gerçek bir adaptörde o bayrağı
dürüstçe doldurmak sözleşmenin kendisidir: `tokens=True` deyip token vermeyen
bir adaptör, altındaki her sayıyı sessizce bozar.
