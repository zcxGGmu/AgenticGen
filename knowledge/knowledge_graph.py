"""
知识图谱构建和查询系统
支持实体识别、关系抽取和图查询
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from collections import defaultdict, deque

from ai_models.model_manager import ModelManager
from cache.multi_level_cache import MultiLevelCache

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """实体类"""
    id: str
    type: str
    name: str
    description: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Relation:
    """关系类"""
    id: str
    subject: str  # 主语实体ID
    predicate: str  # 谓语/关系类型
    object: str  # 宾语实体ID
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class GraphPath:
    """图路径"""
    entities: List[str]  # 实体ID序列
    relations: List[str]  # 关系ID序列
    score: float = 1.0
    description: str = ""


class KnowledgeGraph:
    """知识图谱"""

    def __init__(self):
        self.model_manager = ModelManager()
        self.cache = MultiLevelCache()

        # 图存储
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}

        # 索引
        self.entity_index: Dict[str, Set[str]] = defaultdict(set)  # type -> entity_ids
        self.relation_index: Dict[str, Set[str]] = defaultdict(set)  # predicate -> relation_ids
        self.adjacency: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))  # subject -> predicate -> objects

        # 实体类型
        self.entity_types = {
            "person", "organization", "location", "product", "technology",
            "concept", "event", "date", "number", "document", "code"
        }

        # 关系类型
        self.relation_types = {
            "is_a", "part_of", "located_in", "created_by", "works_for",
            "related_to", "uses", "implements", "depends_on", "example_of"
        }

        # NLP模型
        self.ner_model = "gpt-4"  # 命名实体识别
        self.re_model = "gpt-4"  # 关系抽取

    async def add_entities_and_relations(
        self,
        text: str,
        source: str = ""
    ) -> Tuple[List[Entity], List[Relation]]:
        """
        从文本中抽取实体和关系
        """
        try:
            logger.info(f"Extracting from: {text[:100]}...")

            # 实体识别
            entities = await self._extract_entities(text, source)

            # 关系抽取
            relations = await self._extract_relations(text, entities, source)

            # 添加到图
            for entity in entities:
                self._add_entity(entity)

            for relation in relations:
                self._add_relation(relation)

            logger.info(f"Extracted {len(entities)} entities and {len(relations)} relations")
            return entities, relations

        except Exception as e:
            logger.error(f"Failed to extract from text: {str(e)}")
            return [], []

    async def _extract_entities(
        self,
        text: str,
        source: str
    ) -> List[Entity]:
        """
        抽取命名实体
        """
        try:
            # 构建NER提示
            prompt = f"""
            Extract named entities from the following text. For each entity, provide:
            - name: the entity text
            - type: one of {list(self.entity_types)}
            - description: brief description

            Text: {text}

            Return as JSON array:
            [
                {{"name": "...", "type": "...", "description": "..."}},
                ...
            ]
            """

            # 调用模型
            response = await self.model_manager.chat_completion(
                model_name=self.ner_model,
                messages=[
                    {"role": "system", "content": "You are a named entity recognition expert."},
                    {"role": "user", "content": prompt}
                ],
                stream=False
            )

            # 解析响应
            try:
                entities_data = json.loads(response["choices"][0]["message"]["content"])
            except:
                entities_data = []

            # 创建实体对象
            entities = []
            for entity_data in entities_data:
                # 生成实体ID
                entity_id = self._generate_entity_id(entity_data["name"])

                entity = Entity(
                    id=entity_id,
                    type=entity_data["type"],
                    name=entity_data["name"],
                    description=entity_data.get("description", ""),
                    source=source
                )
                entities.append(entity)

            return entities

        except Exception as e:
            logger.error(f"Entity extraction failed: {str(e)}")
            return []

    async def _extract_relations(
        self,
        text: str,
        entities: List[Entity],
        source: str
    ) -> List[Relation]:
        """
        抽取实体间关系
        """
        try:
            # 构建关系抽取提示
            entity_list = "\n".join([f"- {e.name} ({e.type})" for e in entities])

            prompt = f"""
            Extract relationships between entities in the following text.

            Entities:
            {entity_list}

            Text: {text}

            For each relationship, provide:
            - subject: entity name
            - predicate: relationship type (one of {list(self.relation_types)} or custom)
            - object: entity name
            - description: brief description

            Return as JSON array:
            [
                {{"subject": "...", "predicate": "...", "object": "...", "description": "..."}},
                ...
            ]
            """

            # 调用模型
            response = await self.model_manager.chat_completion(
                model_name=self.re_model,
                messages=[
                    {"role": "system", "content": "You are a relationship extraction expert."},
                    {"role": "user", "content": prompt}
                ],
                stream=False
            )

            # 解析响应
            try:
                relations_data = json.loads(response["choices"][0]["message"]["content"])
            except:
                relations_data = []

            # 创建关系对象
            relations = []
            entity_name_to_id = {e.name: e.id for e in entities}

            for rel_data in relations_data:
                subject_name = rel_data["subject"]
                object_name = rel_data["object"]

                if subject_name in entity_name_to_id and object_name in entity_name_to_id:
                    relation_id = self._generate_relation_id(
                        entity_name_to_id[subject_name],
                        rel_data["predicate"],
                        entity_name_to_id[object_name]
                    )

                    relation = Relation(
                        id=relation_id,
                        subject=entity_name_to_id[subject_name],
                        predicate=rel_data["predicate"],
                        object=entity_name_to_id[object_name],
                        description=rel_data.get("description", ""),
                        source=source
                    )
                    relations.append(relation)

            return relations

        except Exception as e:
            logger.error(f"Relation extraction failed: {str(e)}")
            return []

    def _add_entity(self, entity: Entity):
        """添加实体到图谱"""
        if entity.id in self.entities:
            # 合并现有实体
            existing = self.entities[entity.id]
            if entity.source not in existing.properties.get("sources", []):
                existing.properties.setdefault("sources", []).append(entity.source)
        else:
            self.entities[entity.id] = entity
            self.entity_index[entity.type].add(entity.id)

    def _add_relation(self, relation: Relation):
        """添加关系到图谱"""
        if relation.id not in self.relations:
            self.relations[relation.id] = relation
            self.relation_index[relation.predicate].add(relation.id)

            # 更新邻接表
            self.adjacency[relation.subject][relation.predicate].add(relation.object)

    async def find_entity(
        self,
        name: str,
        entity_type: Optional[str] = None
    ) -> Optional[Entity]:
        """
        查找实体
        """
        # 精确匹配
        for entity in self.entities.values():
            if entity.name.lower() == name.lower():
                if entity_type is None or entity.type == entity_type:
                    return entity

        # 模糊匹配
        best_match = None
        best_score = 0

        for entity in self.entities.values():
            if entity_type is not None and entity.type != entity_type:
                continue

            # 计算相似度
            similarity = self._calculate_similarity(name.lower(), entity.name.lower())
            if similarity > best_score and similarity > 0.8:
                best_score = similarity
                best_match = entity

        return best_match

    async def find_related_entities(
        self,
        entity_id: str,
        relation_type: Optional[str] = None,
        direction: str = "both"  # "out", "in", "both"
    ) -> List[Tuple[Entity, Relation]]:
        """
        查找相关实体
        """
        related = []
        entity = self.entities.get(entity_id)

        if not entity:
            return related

        # 出边关系
        if direction in ["out", "both"]:
            if entity_id in self.adjacency:
                for predicate, objects in self.adjacency[entity_id].items():
                    if relation_type is None or predicate == relation_type:
                        for obj_id in objects:
                            obj_entity = self.entities.get(obj_id)
                            if obj_entity:
                                # 找到对应的关系
                                relation = next(
                                    (r for r in self.relations.values()
                                     if r.subject == entity_id and
                                        r.predicate == predicate and
                                        r.object == obj_id),
                                    None
                                )
                                if relation:
                                    related.append((obj_entity, relation))

        # 入边关系
        if direction in ["in", "both"]:
            for relation in self.relations.values():
                if relation.object == entity_id:
                    if relation_type is None or relation.predicate == relation_type:
                        subject_entity = self.entities.get(relation.subject)
                        if subject_entity:
                            related.append((subject_entity, relation))

        return related

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5
    ) -> List[GraphPath]:
        """
        查找实体间路径
        """
        paths = []

        # BFS搜索
        queue = deque([(source_id, [], [])])
        visited = set()

        while queue:
            current_id, entity_path, relation_path = queue.popleft()

            if current_id == target_id:
                # 找到目标，构建路径
                final_entities = [source_id] + entity_path + [target_id]
                paths.append(GraphPath(
                    entities=final_entities,
                    relations=relation_path,
                    score=1.0 / (len(entity_path) + 1),
                    description=self._describe_path(final_entities, relation_path)
                ))
                continue

            if len(entity_path) >= max_depth:
                continue

            if current_id in visited:
                continue

            visited.add(current_id)

            # 遍历邻居
            if current_id in self.adjacency:
                for predicate, objects in self.adjacency[current_id].items():
                    for obj_id in objects:
                        # 找到对应的关系ID
                        relation = next(
                            (r.id for r in self.relations.values()
                             if r.subject == current_id and
                                r.predicate == predicate and
                                r.object == obj_id),
                            ""
                        )

                        queue.append((
                            obj_id,
                            entity_path + [obj_id],
                            relation_path + [relation]
                        ))

        # 按分数排序
        paths.sort(key=lambda x: x.score, reverse=True)

        return paths

    async def query_graph(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        自然语言图查询
        """
        try:
            # 解析查询意图
            intent = await self._parse_query_intent(query)

            # 执行查询
            if intent["type"] == "entity_search":
                results = await self._execute_entity_search(intent, limit)
            elif intent["type"] == "relation_search":
                results = await self._execute_relation_search(intent, limit)
            elif intent["type"] == "path_search":
                results = await self._execute_path_search(intent, limit)
            else:
                results = []

            return results

        except Exception as e:
            logger.error(f"Graph query failed: {str(e)}")
            return []

    async def _parse_query_intent(self, query: str) -> Dict[str, Any]:
        """
        解析查询意图
        """
        prompt = f"""
        Analyze the following graph query and extract the intent.

        Query: {query}

        Determine if this is:
        1. Entity search: looking for entities of a certain type
        2. Relation search: looking for entities with certain relationships
        3. Path search: looking for connections between entities

        Return as JSON:
        {{
            "type": "entity_search|relation_search|path_search",
            "entities": ["entity names mentioned"],
            "entity_types": ["entity types mentioned"],
            "relations": ["relation types mentioned"],
            "constraints": {{"key": "value"}}
        }}
        """

        response = await self.model_manager.chat_completion(
            model_name="gpt-4",
            messages=[
                {"role": "system", "content": "You are a graph query analyzer."},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )

        try:
            return json.loads(response["choices"][0]["message"]["content"])
        except:
            return {"type": "entity_search", "entities": [], "entity_types": [], "relations": []}

    async def _execute_entity_search(
        self,
        intent: Dict[str, Any],
        limit: int
    ) -> List[Dict[str, Any]]:
        """执行实体搜索"""
        results = []

        # 根据类型筛选
        entity_types = intent.get("entity_types", [])
        candidate_entities = []

        if entity_types:
            for entity_type in entity_types:
                candidate_entities.extend(
                    self.entities[eid] for eid in self.entity_index.get(entity_type, set())
                )
        else:
            candidate_entities = list(self.entities.values())

        # 根据名称筛选
        entities_mentioned = intent.get("entities", [])
        if entities_mentioned:
            filtered_entities = []
            for entity in candidate_entities:
                for name in entities_mentioned:
                    if name.lower() in entity.name.lower():
                        filtered_entities.append(entity)
                        break
            candidate_entities = filtered_entities

        # 返回结果
        for entity in candidate_entities[:limit]:
            results.append({
                "type": "entity",
                "id": entity.id,
                "name": entity.name,
                "entity_type": entity.type,
                "description": entity.description,
                "properties": entity.properties
            })

        return results

    async def _execute_relation_search(
        self,
        intent: Dict[str, Any],
        limit: int
    ) -> List[Dict[str, Any]]:
        """执行关系搜索"""
        results = []
        relation_types = intent.get("relations", [])

        candidate_relations = []
        if relation_types:
            for rel_type in relation_types:
                candidate_relations.extend(
                    self.relations[rid] for rid in self.relation_index.get(rel_type, set())
                )
        else:
            candidate_relations = list(self.relations.values())

        for relation in candidate_relations[:limit]:
            subject = self.entities.get(relation.subject)
            obj = self.entities.get(relation.object)

            results.append({
                "type": "relation",
                "id": relation.id,
                "predicate": relation.predicate,
                "subject": subject.name if subject else "Unknown",
                "object": obj.name if obj else "Unknown",
                "description": relation.description,
                "properties": relation.properties
            })

        return results

    async def _execute_path_search(
        self,
        intent: Dict[str, Any],
        limit: int
    ) -> List[Dict[str, Any]]:
        """执行路径搜索"""
        results = []
        entities = intent.get("entities", [])

        if len(entities) >= 2:
            source_entity = await self.find_entity(entities[0])
            target_entity = await self.find_entity(entities[1])

            if source_entity and target_entity:
                paths = await self.find_path(source_entity.id, target_entity.id)

                for path in paths[:limit]:
                    results.append({
                        "type": "path",
                        "entities": [self.entities[eid].name for eid in path.entities],
                        "relations": path.relations,
                        "score": path.score,
                        "description": path.description
                    })

        return results

    def _generate_entity_id(self, name: str) -> str:
        """生成实体ID"""
        # 标准化名称
        normalized = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
        return f"entity_{normalized}_{hash(name) % 1000000}"

    def _generate_relation_id(
        self,
        subject_id: str,
        predicate: str,
        object_id: str
    ) -> str:
        """生成关系ID"""
        normalized_pred = re.sub(r'[^a-zA-Z0-9]', '_', predicate.lower())
        return f"rel_{subject_id}_{normalized_pred}_{object_id}"

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """计算字符串相似度"""
        # 简单的相似度计算
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 or not words2:
            return 0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def _describe_path(
        self,
        entity_ids: List[str],
        relation_ids: List[str]
    ) -> str:
        """描述路径"""
        description_parts = []

        for i in range(len(entity_ids) - 1):
            subject = self.entities.get(entity_ids[i])
            obj = self.entities.get(entity_ids[i + 1])

            if i < len(relation_ids):
                relation = self.relations.get(relation_ids[i])
                if relation:
                    description_parts.append(
                        f"{subject.name if subject else 'Unknown'} "
                        f"{relation.predicate.replace('_', ' ')} "
                        f"{obj.name if obj else 'Unknown'}"
                    )

        return " -> ".join(description_parts)

    async def get_statistics(self) -> Dict[str, Any]:
        """获取图谱统计信息"""
        return {
            "entity_count": len(self.entities),
            "relation_count": len(self.relations),
            "entity_types": {
                etype: len(self.entity_index.get(etype, set()))
                for etype in self.entity_types
            },
            "relation_types": {
                rtype: len(self.relation_index.get(rtype, set()))
                for rtype in self.relation_types
            },
            "avg_relations_per_entity": len(self.relations) / max(1, len(self.entities))
        }


# 全局实例
knowledge_graph = KnowledgeGraph()