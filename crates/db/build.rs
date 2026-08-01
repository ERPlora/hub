use std::{collections::HashSet, env, fs, path::PathBuf};

use serde::Deserialize;

#[derive(Deserialize)]
struct SqlBridgeContract {
    schema_version: u32,
    functions: Vec<String>,
}

fn main() {
    let manifest_dir = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let contract_path = manifest_dir.join("../../schemas/sql-bridge-functions.json");
    println!("cargo:rerun-if-changed={}", contract_path.display());

    let raw = fs::read_to_string(&contract_path)
        .unwrap_or_else(|error| panic!("{}: {error}", contract_path.display()));
    let contract: SqlBridgeContract = serde_json::from_str(&raw)
        .unwrap_or_else(|error| panic!("{}: {error}", contract_path.display()));
    assert_eq!(
        contract.schema_version, 1,
        "versión de contrato SQL desconocida"
    );
    assert!(
        !contract.functions.is_empty(),
        "el contrato SQL no puede estar vacío"
    );

    let mut seen = HashSet::new();
    for function in &contract.functions {
        assert!(
            function.starts_with("erp_")
                && function
                    .bytes()
                    .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_'),
            "función-puente inválida: {function}"
        );
        assert!(
            seen.insert(function),
            "función-puente duplicada: {function}"
        );
    }

    let generated = format!(
        "&[{}]",
        contract
            .functions
            .iter()
            .map(|function| format!("{function:?}"))
            .collect::<Vec<_>>()
            .join(", ")
    );
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap()).join("sql_bridge_functions.rs");
    fs::write(out, generated).expect("escribir contrato SQL generado");
}
