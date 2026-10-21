fn main() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
    println!("cargo:rustc-env=AFS_DEFAULT_WORKSPACE={}", root.display());
    tauri_build::build()
}
