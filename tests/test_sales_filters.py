from app.db_models import SalesLead, Workspace


def test_sales_category_filter_only_shows_requested_sector(registered_client, db):
    client = registered_client("owner@platform.az", "The Agency")
    workspace = db.query(Workspace).filter(Workspace.name == "The Agency").one()
    workspace.slug = "legacy"
    db.add_all([
        SalesLead(workspace_id=workspace.id, company_name="Beauty One", category="beauty", city="Bakı", source_external_id="beauty-1", score=80, status="NEW"),
        SalesLead(workspace_id=workspace.id, company_name="Old Restaurant", category="restaurant", city="Bakı", source_external_id="restaurant-1", score=90, status="NEW"),
    ])
    db.commit()

    response = client.get("/sales?found=0&category=beauty&city=Bakı&country=Azərbaycan")

    assert response.status_code == 200
    assert "Beauty One" in response.text
    assert "Old Restaurant" not in response.text
    assert "yalnız <b>Beauty</b> · <b>Bakı</b> nəticələri" in response.text
    assert 'value="beauty" selected' in response.text


def test_sales_city_filter_excludes_other_cities(registered_client, db):
    """Canlı istifadəçi tapıntısı: İstanbul axtarışında Bakıdakı köhnə (yüksək xallı) lead
    öndə çıxırdı, çünki nəticə ekranı yalnız kateqoriyaya görə süzürdü, şəhərə görə yox."""
    client = registered_client("owner@platform.az", "The Agency")
    workspace = db.query(Workspace).filter(Workspace.name == "The Agency").one()
    workspace.slug = "legacy"
    db.add_all([
        SalesLead(workspace_id=workspace.id, company_name="Baku High Score", category="restaurant", city="Bakı, Azərbaycan", source_external_id="baku-1", score=100, status="NEW"),
        SalesLead(workspace_id=workspace.id, company_name="Istanbul Match", category="restaurant", city="İstanbul, Türkiyə", source_external_id="ist-1", score=70, status="NEW"),
    ])
    db.commit()

    response = client.get("/sales?found=1&category=restaurant&city=İstanbul&country=Türkiyə")

    assert "Istanbul Match" in response.text
    assert "Baku High Score" not in response.text


def test_sales_city_filter_handles_azerbaijani_dotless_i(registered_client, db):
    """Canlı istifadəçi tapıntısı: "baki" (adi i) yazanda "Bakı, Azərbaycan" (Azərbaycan ı)
    üçün SQL ILIKE uyğunluq tapmırdı — nəticədə mövcud lead-lər "yoxdur" kimi görünürdü."""
    client = registered_client("owner@platform.az", "The Agency")
    workspace = db.query(Workspace).filter(Workspace.name == "The Agency").one()
    workspace.slug = "legacy"
    db.add(SalesLead(
        workspace_id=workspace.id, company_name="Baki Beauty Salon", category="beauty",
        city="Bakı, Azərbaycan", source_external_id="baku-beauty-1", score=80, status="NEW",
    ))
    db.commit()

    response = client.get("/sales?found=1&category=beauty&city=baki&country=azerbaycan")

    assert "Baki Beauty Salon" in response.text
    assert "Hələ lead yoxdur" not in response.text


def test_sales_without_filter_still_shows_full_crm(registered_client, db):
    client = registered_client("owner@platform.az", "The Agency")
    workspace = db.query(Workspace).filter(Workspace.name == "The Agency").one()
    workspace.slug = "legacy"
    db.add_all([
        SalesLead(workspace_id=workspace.id, company_name="Beauty One", category="beauty", city="Bakı", source_external_id="beauty-1", score=80, status="NEW"),
        SalesLead(workspace_id=workspace.id, company_name="Old Restaurant", category="restaurant", city="Bakı", source_external_id="restaurant-1", score=90, status="NEW"),
    ])
    db.commit()

    response = client.get("/sales")

    assert "Beauty One" in response.text
    assert "Old Restaurant" in response.text
