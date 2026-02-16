backend/
  app/
    main.py                  # FastAPI app 생성, router include, CORS
    core/
      config.py              # env 로드 (SUPABASE_URL, KEY, SIGNED_TTL 등)
      cors.py                # allowed origins (Vercel)
    db/
      supabase_client.py     # create_client()
      repositories/
        disease_repo.py
        gene_repo.py
        region_repo.py
        snv_repo.py
        window_repo.py
        state_repo.py
        baseline_repo.py     # (Step3)
    services/
      storage_service.py     # signed url 생성(B방식)
      disease_service.py     # Step1/2 조합 로직
      state_service.py       # state 생성
    api/
      router.py              # /api 라우터 묶기
      routes/
        diseases.py          # Step1/Step2-1
        states.py            # Step2-2
        baseline.py          # Step3 placeholder
        splicing.py          # Step3 placeholder
        structure.py         # Step4 placeholder
    schemas/
      disease.py
      gene.py
      region.py
      state.py
      common.py              # ErrorResponse, ListResponse 등
    utils/
      genetics.py            # (필요시) 서열/좌표 유틸
  pyproject.toml             # uv 관리
  uv.lock
  Dockerfile                 # 다음 단계(3)에서 작성
  .env.example
  README.md