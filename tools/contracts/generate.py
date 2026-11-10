"""从唯一OpenAPI源生成结构产物；核对模式不修改纳管输出。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent


from contract_source import HTTP_METHODS, UniqueLoader, operations, load_spec, project, save


def generate(spec_path: Path, output: Path) -> None:
    """在空目录生成模型、类型、校验器及可追溯摘要。"""
    spec = load_spec(spec_path)
    if output.exists() and any(output.iterdir()):
        raise ValueError("生成目标必须为空目录")
    output.mkdir(parents=True, exist_ok=True)
    definitions = project(spec["components"]["schemas"])
    target = spec["info"]["version"] in {"1.0.0", "1.1.0", "2.0.0", "3.0.0"}
    if target:
        from projection import projection
        projected = projection(spec, hashlib.sha256(spec_path.read_bytes()).hexdigest())
        for item in projected["boundaries"].values():
            if item["validator"] in definitions:
                raise ValueError("边界导出名冲突")
            definitions[item["validator"]] = item["schema"]
        (output / "openapi.resource").write_bytes(spec_path.read_bytes())
    else:
        projected = project({"paths": spec["paths"], "transport": spec["x-wolf-current-transport"],
                             "coverage": spec["x-wolf-coverage"]})
    save(output / "schemas.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": definitions})
    save(output / "operations.json", projected)
    # 直接使用OpenAPI模型输入，不生成或挂接HTTP服务器，避免改变现有响应过滤。
    subprocess.run([sys.executable, "-m", "datamodel_code_generator", "--input", str(spec_path),
        "--input-file-type", "openapi", "--output", str(output / "http_dto.py"),
        "--output-model-type", "pydantic_v2.BaseModel", "--target-python-version", "3.11",
        "--strict-types", "str", "int", "float", "bool", "--field-constraints",
        "--enum-field-as-literal", "all",
        "--strict-nullable", "--formatters", "black", "isort",
        "--use-standard-collections", "--use-union-operator", "--disable-timestamp",
        "--custom-file-header", "# 自动生成：只修改 contracts/openapi.yaml，禁止手工修补。"], check=True)
    node_dependencies = Path(os.environ.get("THEWOLF_CONTRACT_NODE_DEPS", TOOLS / "node_modules")).resolve()
    subprocess.run(["node", str(TOOLS / "generate.mjs"), str(spec_path), str(output), str(node_dependencies)], check=True)
    save(output / "manifest.json", {
        "source_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
        "python": {name: importlib.metadata.version(name) for name in
                   ("datamodel-code-generator", "pydantic", "PyYAML", "jsonschema", "openapi-spec-validator")},
        "inputs": {name: hashlib.sha256((TOOLS / name).read_bytes()).hexdigest()
                   for name in ("generate.py", "generate.mjs", "contract_source.py", "projection.py", "package-lock.json", "requirements.lock")},
        "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())},
        "editable": False,
        # 此处登记装配预期，实际实现/语义证据由check_browser及产品测试给出。
        "product_runtime_integrated_operations": ([method.upper() + " " + path for path, method, _ in operations(spec)] if target else spec["x-wolf-coverage"].get("runtime_integrated_operations", [])),
        "product_runtime_profile": "RB-RO-1: read; POST disabled; no native host" if target else "B-current",
        "format": "wolf-generation/C-target/1" if target else "wolf-generation/B-current/1",
        "source_version": spec["info"]["version"]})


def runtime_projection(generated: Path, output: Path, *, check: bool = False) -> None:
    """将同源模型和Schema机械投影到Python包；核对模式拒绝产品副本漂移。

    Args:
        generated: 本次完整生成目录，不接受手改的字段映射。
        output: 产品HTTP契约包目录，仅写入明确列出的三个派生文件。
        check: 只比较字节；不创建或修补产品文件。
    Raises:
        ValueError: 产品投影与本次生成不一致。
    """
    names = [("http_dto.py", "models.py"), ("schemas.json", "schemas.json"),
             ("manifest.json", "generation.json")]
    if (generated / "openapi.resource").is_file():
        names += [("openapi.resource", "openapi.resource"), ("operations.json", "operations.json")]
    for source, target in names:
        content = (generated / source).read_bytes()
        if check:
            if not (output / target).is_file() or (output / target).read_bytes() != content:
                raise ValueError(f"产品投影漂移: {target}")
        else:
            output.mkdir(parents=True, exist_ok=True)
            (output / target).write_bytes(content)


def main() -> None:
    """生成到新目录或与纳管输出逐字比较；不会在线安装依赖。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=ROOT / "contracts/openapi.yaml")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--runtime-output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if args.output or args.runtime_output:
            parser.error("--check不能同时写输出目录")
        with tempfile.TemporaryDirectory(prefix="thewolf-contract-generate-", dir="/private/tmp") as directory:
            generated = Path(directory)
            generate(args.spec.resolve(), generated)
            expected = ROOT / "contracts/generated"
            actual_names = {p.name for p in generated.iterdir()}
            if actual_names != {p.name for p in expected.iterdir() if p.is_file()}:
                raise ValueError("生成文件集合发生漂移")
            for name in actual_names:
                if (generated / name).read_bytes() != (expected / name).read_bytes():
                    raise ValueError(f"生成漂移: {name}")
            runtime_projection(generated, ROOT / "python/src/pmi/http_contract", check=True)
        print("契约可重复生成检查通过")
    elif args.output:
        generate(args.spec.resolve(), args.output.resolve())
        if args.runtime_output:
            runtime_projection(args.output.resolve(), args.runtime_output.resolve())
    else:
        parser.error("指定空--output目录，或使用--check")


if __name__ == "__main__":
    main()
