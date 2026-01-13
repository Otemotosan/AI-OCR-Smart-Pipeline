# Google Cloud Initial Setup Guide

このガイドでは、AI-OCR Smart Pipelineに必要なGoogle Cloud環境の初期セットアップ手順を説明します。

---

## 1. アカウントとプロジェクトの作成

1.  **Google Cloud アカウントの作成**
    *   [Google Cloud コンソール](https://console.cloud.google.com/) にアクセスし、Googleアカウントでログイン（または新規作成）します。
    *   初回利用時は利用規約への同意が必要です。また、**90日間の$300無料クレジット**が利用できる場合があります。

2.  **プロジェクトの作成**
    *   画面左上のプロジェクト選択プルダウンから「新しいプロジェクト」をクリックします。
    *   **プロジェクト名**: 任意の名前（例: `ai-ocr-pipeline`）
    *   **プロジェクトID**: 一意のIDが自動生成されますが、編集可能です（作成後は変更不可）。これをメモしておいてください。
    *   「作成」をクリックします。

3.  **請求（Billing）の有効化**
    *   プロジェクト作成後、メニューの「お支払い」から請求先アカウントをリンクします。
    *   ※ Google Cloudの機能を利用するには、無料枠内であってもクレジットカード等の登録が必要です。

---

## 2. ローカル開発環境のセットアップ (Windows)

Google Cloudをコマンドラインから操作するための `gcloud` CLI をインストールします。

1.  **Google Cloud CLI のインストーラーをダウンロード**
    *   [こちらのリンク](https://cloud.google.com/sdk/docs/install?hl=ja#windows) から「Google Cloud CLI インストーラ」をダウンロードして実行します。
    *   インストール設定はデフォルトのままで問題ありません。

2.  **初期設定 (gcloud init)**
    *   インストール完了後、PowerShellまたはコマンドプロンプトを開き、以下のコマンドを実行します。
        ```powershell
        gcloud init
        ```
    *   ブラウザが開き、Googleアカウントの認証を求められます。「許可」をクリックします。
    *   コンソールに戻り、先ほど作成したプロジェクトを選択します。

3.  **Application Default Credentials (ADC) の設定**
    *   ローカルからPythonコードを実行してGoogle Cloudにアクセスするために必要です。
        ```powershell
        gcloud auth application-default login
        ```
    *   再度ブラウザで認証を行ってください。

---

## 3. 必要なAPIの有効化

プロジェクトで使用するサービス（API）を有効化します。以下のコマンドをPowerShellで実行してください。

```powershell
# プロジェクトIDを設定 (各自のIDに置き換えてください)
gcloud config set project [YOUR_PROJECT_ID]

# 必要なAPIを一括有効化
gcloud services enable `
  cloudfunctions.googleapis.com `
  run.googleapis.com `
  firestore.googleapis.com `
  storage.googleapis.com `
  aiplatform.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  cloudresourcemanager.googleapis.com
```

**有効化するAPIの役割:**
*   `cloudfunctions`: OCR処理のバックエンド
*   `run`: 管理画面 (Web UI) のホスティング
*   `firestore`: データと処理状態の管理
*   `storage`: ファイル (PDF/画像) の保存
*   `aiplatform`: Gemini (Vertex AI) の利用
*   `cloudbuild`: CI/CD パイプライン

---

## 4. Firestore データベースの作成

Firestoreは「ネイティブモード」で作成する必要があります。

1.  Cloudコンソールの検索バーで「Firestore」を検索・選択します。
2.  「データベースの作成」をクリックします。
3.  **モード選択**: 「**ネイティブモード**」を選択（重要）。
4.  **ロケーション**: `asia-northeast1` (東京) を推奨します。
5.  「データベースを作成」をクリックします。

---

以上で初期セットアップは完了です。
