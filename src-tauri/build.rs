fn main() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
    let workspace=std::env::var("AFS_BUILD_WORKSPACE").unwrap_or_else(|_|root.display().to_string());
    println!("cargo:rerun-if-env-changed=AFS_BUILD_WORKSPACE");
    println!("cargo:rustc-env=AFS_DEFAULT_WORKSPACE={}", workspace);
    tauri_build::build()
}
