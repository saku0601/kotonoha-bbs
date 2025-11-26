# Corkboard BBS

Flaskベースのコルクボード掲示板アプリケーション

## 機能

- ユーザー認証（ログイン/ログアウト）
- 投稿機能（タイトル、カテゴリ、内容、ファイル添付）
- コメント機能
- 投稿・コメントの編集・削除
- 管理者機能（ユーザー管理、ファイル管理）
- Firebase Storage連携（ファイル保存）

## Renderへのデプロイ手順

### 1. リポジトリの準備

1. GitHubにリポジトリを作成し、コードをプッシュします
2. Renderアカウントにログインします（https://render.com）

### 2. データベースの作成

1. Renderダッシュボードで「New +」→「PostgreSQL」を選択
2. データベース名を設定（例: `corkboard-db`）
3. プランを選択（Freeプランでも動作します）
4. 「Create Database」をクリック
5. データベースが作成されたら、接続文字列（Internal Database URL）をコピーしておきます

### 3. Webサービスの作成

#### 方法A: render.yamlを使用する場合（推奨）

1. Renderダッシュボードで「New +」→「Blueprint」を選択
2. GitHubリポジトリを接続
3. `render.yaml`ファイルが自動的に検出されます
4. 環境変数を設定：
   - `SECRET_KEY`: ランダムな文字列（例: `python -c "import secrets; print(secrets.token_hex(32))"`で生成）
   - `FIREBASE_SERVICE_ACCOUNT`: FirebaseサービスアカウントキーのJSON文字列
   - `FIREBASE_STORAGE_BUCKET`: Firebase Storageバケット名（デフォルト: `kotonoha-bbs.firebasestorage.app`）
5. 「Apply」をクリックしてデプロイ

#### 方法B: 手動で作成する場合

1. Renderダッシュボードで「New +」→「Web Service」を選択
2. GitHubリポジトリを接続
3. 以下の設定を行います：
   - **Name**: `corkboard-bbs`（任意）
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. 環境変数を追加：
   - `SECRET_KEY`: ランダムな文字列
   - `DATABASE_URL`: ステップ2で作成したデータベースの接続文字列
   - `FIREBASE_SERVICE_ACCOUNT`: FirebaseサービスアカウントキーのJSON文字列
   - `FIREBASE_STORAGE_BUCKET`: Firebase Storageバケット名
5. 「Create Web Service」をクリックしてデプロイ

### 4. 環境変数の設定

Renderダッシュボードの「Environment」タブで以下の環境変数を設定します：

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `SECRET_KEY` | Flaskのセッション暗号化キー | 必須 |
| `DATABASE_URL` | PostgreSQLデータベースの接続URL | 必須（自動設定される場合あり） |
| `FIREBASE_SERVICE_ACCOUNT` | FirebaseサービスアカウントキーのJSON文字列 | オプション（Firebase使用時） |
| `FIREBASE_STORAGE_BUCKET` | Firebase Storageバケット名 | オプション（デフォルト値あり） |

#### SECRET_KEYの生成方法

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

#### FIREBASE_SERVICE_ACCOUNTの設定方法

1. Firebase Consoleでサービスアカウントキーをダウンロード
2. JSONファイルの内容をそのまま環境変数に設定（改行を含むJSON文字列）

または、Renderの環境変数エディタで「Secret File」としてアップロードすることもできます。

### 5. デプロイの確認

1. デプロイが完了したら、提供されたURLにアクセス
2. ログインページが表示されることを確認
3. デフォルトの管理者アカウントでログイン：
   - ユーザー名: `admin`
   - パスワード: `admin`
4. 初回ログイン後、パスワードを変更することを推奨します

### 6. トラブルシューティング

#### データベース接続エラー

- `DATABASE_URL`が正しく設定されているか確認
- データベースが作成されているか確認
- データベースの接続文字列が`postgresql://`で始まっているか確認（`postgres://`は自動変換されます）

#### Firebase初期化エラー

- `FIREBASE_SERVICE_ACCOUNT`が正しいJSON形式か確認
- Firebase Storageバケットが存在するか確認
- Firebase初期化エラーが発生しても、アプリはローカルストレージにフォールバックします

#### デプロイエラー

- Renderのログを確認（「Logs」タブ）
- `requirements.txt`の依存関係が正しいか確認
- Pythonバージョンが3.11以上であることを確認

## ローカル開発環境のセットアップ

1. リポジトリをクローン
2. 仮想環境を作成・有効化：
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. 依存関係をインストール：
   ```bash
   pip install -r requirements.txt
   ```
4. 環境変数を設定（`.env`ファイルを作成）：
   ```
   SECRET_KEY=your_secret_key_here
   DATABASE_URL=sqlite:///instance/corkboard.sqlite
   FIREBASE_SERVICE_ACCOUNT={"type":"service_account",...}
   FIREBASE_STORAGE_BUCKET=kotonoha-bbs.firebasestorage.app
   ```
5. アプリケーションを起動：
   ```bash
   python app.py
   ```
6. ブラウザで `http://localhost:5000` にアクセス

## 注意事項

- RenderのFreeプランでは、一定時間アクセスがないとスリープします
- 本番環境では必ず`SECRET_KEY`を強力な値に設定してください
- 管理者パスワードは初回ログイン後に変更してください
- Firebase Storageを使用しない場合、ファイルはローカルストレージに保存されます（Renderでは永続化されません）

## ライセンス

このプロジェクトのライセンス情報は含まれていません。

